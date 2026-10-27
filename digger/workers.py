"""
Processes for track analysis (the pipeline).

Analyzer is a process pool: while the network downloads the next track, the previous ones are
analysed in parallel on other cores. The number of processes is cores minus one (one stays for the
window and the player), but no more than three and no more than memory allows. The processes run at
a lower priority and with a limited number of FFT/BLAS threads, so they don't disturb each other or
the jam. If the processes fail to start or keep crashing, analysis runs in a daemon thread,
so the pipeline watchdog can still interrupt waiting.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from concurrent.futures import Future, ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from .i18n import T

MAX_WORKERS = 3
GB_PER_WORKER = 2.5          # very generous: one analysis peaks at ~0.2-0.35 GB, the rest is for the OS and browser
MAX_CRASHES = 2              # after this many pool crashes we switch to a single thread
_FALLBACK_SLOT = threading.Semaphore(1)  # includes stopped jobs whose native DSP is still finishing


def total_ram_gb() -> float | None:
    """Physical memory of the computer in GB (None if it can't be determined)."""
    try:
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 2 ** 30
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
    except Exception:
        return None


def worker_count(tasks: int | None = None) -> int:
    """How many analysis processes to start (YTDIGGER_WORKERS=0 — no processes, single thread)."""
    env = os.environ.get("YTDIGGER_WORKERS", os.environ.get("CRATEDIGGER_WORKERS", "")).strip()
    if env.isdigit():
        return int(env) if not tasks else min(int(env), max(1, tasks))
    n = max(1, min(MAX_WORKERS, (os.cpu_count() or 1) - 1))
    ram = total_ram_gb()
    if ram:
        n = max(1, min(n, int(ram // GB_PER_WORKER)))
    if tasks:
        n = max(1, min(n, tasks))
    return n


def _init_worker(threads: int):
    """Start of an analysis process: lower priority and its own FFT thread limit."""
    try:
        if os.name == "nt":
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), 0x4000)       # BELOW_NORMAL_PRIORITY_CLASS
        else:
            os.setsid()  # decoders inherit this analysis-owned process group
            os.environ["YTDIGGER_ANALYSIS_GROUP"] = str(os.getpid())
            os.nice(5)
    except Exception:
        pass
    from . import spec, core, dsp  # noqa: F401  (numpy/scipy load now, not on the first track)
    if os.name == "nt":
        dsp.own_analysis_process()
    spec.FFT_WORKERS = threads


def _ping() -> int:
    """No-op task used to make the processes start right away (while the search is running)."""
    return os.getpid()


class Analyzer:
    """Pool of analysis processes with a fallback to a daemon thread."""

    def __init__(self, log, tasks: int | None = None, tmp: Path | None = None,
                 on_start=None, on_finish=None):
        self.log = log
        self.n = worker_count(tasks)
        self.tmp = tmp
        self.ex: ProcessPoolExecutor | None = None
        self.crashes = 0
        self._lock = threading.RLock()
        self._closed = threading.Event()
        self._on_start = on_start or (lambda: None)
        self._on_finish = on_finish or (lambda: None)
        self._fallbacks = set()
        if self.tmp:
            Path(self.tmp).mkdir(parents=True, exist_ok=True)
        self._start()

    def _clean_tmp(self):
        """Delete temporary decoded audio files (an_*.s16) left in the tmp folder."""
        if not self.tmp:
            return
        try:
            Path(self.tmp).mkdir(parents=True, exist_ok=True)
            for f in Path(self.tmp).glob("an_*.s16"):
                try:
                    f.unlink()
                except OSError:
                    pass
        except OSError:
            pass

    @property
    def parallel(self) -> bool:
        return self.ex is not None

    def _start(self):
        """Create the process pool (or stay in single-thread mode if that's impossible)."""
        if self.n <= 0:                         # CRATEDIGGER_WORKERS=0 — like before 1.2, single thread
            self.n = 1
            return
        try:
            import multiprocessing as mp
            threads = 1  # nested FFT/BLAS teams inflate commit without improving track throughput
            for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
                os.environ[v] = str(threads)                   # only affects newly started processes
            kw = dict(max_workers=self.n, mp_context=mp.get_context("spawn"),
                      initializer=_init_worker, initargs=(threads,))
            if sys.version_info >= (3, 11):
                kw["max_tasks_per_child"] = 8                  # processes get recycled — memory doesn't pile up
            self.ex = ProcessPoolExecutor(**kw)
            for _ in range(self.n):                            # processes start now, while the search is running
                self.ex.submit(_ping)
        except Exception as e:
            self._drop()  # even a failed warm-up may already own live children
            self.log(T("⚠ Parallel analysis unavailable ({e}) — working in a single thread", e=str(e)[:120]))

    def submit(self, fn, *args) -> Future:
        """Hand a task to a process; if the pool is broken, recreate it, and after frequent crashes
        run the task in a daemon thread (still subject to the pipeline watchdog)."""
        with self._lock:
            return self._submit(fn, *args)

    def _submit(self, fn, *args) -> Future:
        if self._closed.is_set():
            f = Future()
            f.cancel()
            return f
        if self.ex is not None:
            try:
                return self.ex.submit(fn, *args)
            except (BrokenProcessPool, RuntimeError):
                self.crashes += 1
                self._drop()
                if self._closed.is_set():
                    return self._submit(fn, *args)
                if self.crashes < MAX_CRASHES:
                    self.log(T("⚠ An analysis process crashed — restarting"))
                    self._start()
                    if self.ex is not None:
                        return self._submit(fn, *args)
                else:
                    self.log(T("⚠ Analysis processes keep crashing — continuing in a single thread"))
        f: Future = Future()
        if self._closed.is_set():
            f.cancel()
            return f

        def work():
            acquired = False
            try:
                while not self._closed.is_set():
                    if _FALLBACK_SLOT.acquire(timeout=0.05):
                        acquired = True
                        break
                if self._closed.is_set() or not f.set_running_or_notify_cancel():
                    f.cancel()
                    return
                from . import dsp
                with dsp.cancellation(self._closed):
                    f.set_result(fn(*args))
            except BaseException as e:   # noqa: BLE001 — the error goes to the caller through the Future
                if not f.done():
                    f.set_exception(e)
            finally:
                if acquired:
                    _FALLBACK_SLOT.release()
                with self._lock:
                    self._fallbacks.discard(threading.current_thread())
                self._on_finish()

        th = threading.Thread(target=work, daemon=True, name="analysis-fallback")
        self._fallbacks.add(th)
        self._on_start()
        try:
            th.start()
        except BaseException:
            self._fallbacks.discard(th)
            self._on_finish()
            raise
        return f

    def _drop(self):
        """Atomically transfer pool ownership to teardown before another kill/finish sees None."""
        with self._lock:
            ex, self.ex = self.ex, None
            if ex is not None:
                self._on_start()
        if ex is not None:
            try:
                self._terminate(ex)
            finally:
                self._on_finish()

    def kill(self):
        """"Stop": kill the processes immediately (unfinished analyses are abandoned)."""
        self._closed.set()
        self._drop()

    def _terminate(self, ex):
        """Reap killed workers before deleting their owned decoder files."""
        procs = list((getattr(ex, "_processes", None) or {}).values())
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        for p in procs:
            try:
                if os.name != "nt":
                    import signal
                    try:
                        os.killpg(p.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        p.terminate()  # initializer may not have established its group yet
                else:
                    p.terminate()
            except Exception:
                pass
        t = time.time() + 3
        for p in procs:
            try:
                p.join(max(0.0, t - time.time()))
                if p.is_alive():
                    p.kill()
                    p.join(1)
            except Exception:
                pass
        with self._lock:
            if not self._fallbacks and not any(p.is_alive() for p in procs):
                self._clean_tmp()
        self._watch_processes(procs)

    def _watch_processes(self, procs):
        """Keep a stopped job accounted for until even a slow process teardown is over."""
        alive = [p for p in procs if p.is_alive()]
        if not alive:
            return
        self._on_start()

        def reap():
            try:
                for p in alive:
                    p.join()
            finally:
                self._on_finish()

        threading.Thread(target=reap, daemon=True, name="analysis-reaper").start()

    def close(self):
        """Release an already drained pool without blocking the job on process teardown."""
        self._closed.set()
        with self._lock:
            ex, self.ex = self.ex, None
            if ex is not None:
                self._on_start()
        if ex is not None:
            procs = list((getattr(ex, "_processes", None) or {}).values())
            try:
                ex.shutdown(wait=False, cancel_futures=True)
            finally:
                self._watch_processes(procs)
                self._on_finish()
