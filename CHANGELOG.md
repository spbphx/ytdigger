# Changelog

## 1.5.2
- Added YouTube Shorts as a third search source with a matching selector button, remembered selection and translated tooltips. Searches use YouTube's Shorts filter and skip ordinary videos; Shorts accept 5–180 seconds of audio and type beats. Source links and re-runs retain the Shorts source.
- Added compatibility with YouTube's grid-based Shorts search results, including continuation pages and duplicate-result protection, using yt-dlp for network requests and metadata extraction.

## 1.5.1
- One-shot ZIP downloads are named `_{KEY}_{ORIGINAL_SONG_NAME}_{YYYY-MM-DD}_{HH-MM}.zip`, using the source song title instead of the `1shots` prefix. Unicode titles are preserved; characters invalid in file names are replaced.
- Accelerated spectral HPSS median filtering with SciPy's 1D rank filter while preserving repeated-edge boundaries. Older SciPy versions, other dtypes and non-finite arrays retain the previous partition path; dependencies and analysis/selection stages are unchanged.
- YouTube searches now allow type beats; YouTube Music keeps the type-beat filter. Other title, duration and broadcast filters are unchanged.
- Search queries containing three or more user-entered words start unchanged. When the exact query has no new suitable records, digging switches to nonempty extra hints, avoiding queries already exhausted in that dig. Shorter queries retain their existing variations; result filters still follow the selected settings.

## 1.5
- Added a compact six-slot loop mixer in the jam bar. Playing loops fill the slots from left to right with their record covers; stopped loops release their thumbnail elements. Up to six loops can play at once, including starts still loading.
- Every loop starts at 75% with its own gain. Drag its cover up or down for smooth volume changes, or use the arrow keys (Shift for larger steps), Home and End. Right-click a cover, or press Enter while focused, to scroll to that loop. The overall volume control is now called Master. Jam ZIPs preserve individual loop levels.
- Fixed asynchronous playback races: repeated clicks, Stop, Space, and removing a crate invalidate pending starts. Audio loading is shared, finished sources disconnect, and the decoded-audio cache has a 96 MiB budget with active loops protected.
- Fixed concurrent job starts and atomic crate-folder reservation. Stopped jobs retain ownership of their resources until actual background work exits; fallback analysis and abandoned network calls have shared concurrency limits. Temporary downloads and decoded audio are isolated per job.
- Added cooperative fallback cancellation between DSP stages, bounded ffmpeg execution and owned decoder-process lifetimes. Empty decodes clean up their files. The saver releases the last saved audio result while waiting for new work.
- Avoided repeatedly calculating full-track statistics in `sig_at`, and reused the isolation harmonic median. A fixed-seed 10-minute synthetic off-grid pad improved from 14.551 s to 12.375 s in one before/after pair, with byte-identical loop audio and boundaries; gains depend on the source and analysis mode. Analysis workers use one internal FFT/BLAS thread to reduce nested-thread resource use.
- Polling requests no longer overlap or apply responses from a previous polling generation. Server logs use absolute cursors through retention rollover. Audio and ZIP responses stream from disk; exports reuse metadata within each request. Removed Python 3.12-only nested f-string syntax to retain the declared Python 3.10+ compatibility.
- Included the previous fix: `fix: prevent duplicate search results from being processed twice`, with regression coverage for duplicate candidates.

## 1.4.3
- YouTube searches skip live, scheduled and archived broadcasts using service metadata. Metadata checks and download guards prevent streams from reaching audio analysis or holding up a dig; a rejected broadcast does not trigger another download attempt.
- "Download all" now stores Bass Only loops in `<BPM>/BS/<key>/`. Drums Only stays in `<BPM>/DR/`; other loop types keep their key folders. Audio filenames and paths in the Loops folder stay unchanged.
- No-grid pads and vocals are rechecked in short local windows, usually 3–15 seconds with extra room for long or slower phrases. A confirmed local rhythm allows a loop to use its own BPM instead of the shared record tempo.
- Nearby pauses are used to preserve complete phrases before fitting them to an exact number of bars. Stretching is tried first in Stretching mode; pitch fallback prefers changes within 5% and allows at most ±12%, updating the key, Camelot code and saved filename. A phrase that cannot fit within these limits is skipped instead of truncated.
- Fitted phrases without a confirmed source rhythm keep the no-grid label and show their processing in English, Russian and Spanish. Ordinary grid-loop processing is unchanged, and temporary local analysis views share existing track data without retaining a new cache.

## 1.4.2
- "Download all" now puts Drums Only loops into `<BPM>/DR/` inside the ZIP instead of a key folder. Loop names and paths in the Loops folder stay unchanged; other loop types keep their key folders.
- Fixed favorite stars losing their yellow state after background updates or crate changes. Stars respond immediately to clicks, and crate saves no longer overwrite favorite marks. Failed saves restore the previous state and report the error.
- Removed loops and crates now release their stored loop data, favorite state and decoded audio cache. Expired Undo notifications release their references, and audio that finishes loading after a crate is removed cannot start hidden playback or refill its cache.

## 1.4.1
- Hardened shutdown: stopping analysis cannot restart the process pool or launch new fallback tasks; submitting work and closing the pool are synchronized.
- Cleanup continues even if an individual shutdown step fails, without hiding the original processing error. Re-running a record always finalizes its pipeline, including on errors.
- Crates with missing or invalid Camelot keys no longer break rendering or status polling: unknown keys show a dash and are excluded from compatibility highlighting. Crate rendering errors no longer interrupt polling cleanup.
- Smaller YouTube Music / YouTube selector buttons and a refined YTDigger accent color.

## 1.4
- Renamed CrateDigger to YTDigger across the interface, launchers, program messages, credits and Model:Samples ZIP names. New installations save to `Music/YTDigger`; an existing `Music/CrateDigger` folder is reused. The `YTDIGGER_WORKERS` setting also accepts the legacy `CRATEDIGGER_WORKERS` environment variable.
- Added a YouTube Music / YouTube search selector beside the language flags. YouTube Music remains the default and the selected service is remembered. YouTube searches all videos without the official-audio restriction, so results may also include podcasts and Type Beats.
- Saved track metadata, source links, credits and re-downloads when re-running a record follow the selected service; older crates remain compatible.
- Added timeouts and saving-thread health checks so stalled analysis or saving reports an error instead of waiting indefinitely. Final draining and process teardown no longer wait without a limit, and late results clean up their temporary source files.
- Limited queued analysis results, including local imports, to control memory use. If worker processes fail, analysis falls back to a daemon thread so the pipeline can still stop waiting.

## 1.3.3
- Scissors ✂ button on "drums only" loops: cuts the loop into one-shot samples and downloads them all as one ZIP. The button sits in the loop's action row, next to favorite / save / remove. All action buttons are the same size (34 px); the four buttons of a "drums only" loop stand with no gap, and the three buttons of other loops are spaced wider so both rows have the same total width.
- The one-shot ZIP is named `1shots_<key>_<date>_<time>.zip` (e.g. `1shots_Amin_2026-10-22_05-07.zip`).
- One-shot detection was rebuilt for dense funk breaks: onsets are pooled from three spectral bands plus the full-band envelope (a new hit is often masked in the full envelope by the tail of the previous one, but always rises in its own band — a hat high, a kick low), each candidate must show a real energy step big enough for that band, and every segment is rescanned so hits that were still masked split it. The result is a true one-shot per hit: a loop that used to give 24 samples with several hits inside now gives 32 clean ones (16ths of both bars).

## 1.3.2
- "Download jam" button in the jam bar: a ZIP of the loops playing now, each pitched exactly as it plays in the jam (speed = master BPM / loop BPM), named after the master loop (`Gmaj95-<date>-<time>.zip`). The key and BPM at the start of each loop name change to the values after the pitch shift.

## 1.3.1
- Key highlighting during a jam follows the master loop (the first one started) and takes the pitch shift into account: every next loop is played at the master's tempo, so e.g. Fmin 75 and F#min 80 are outlined under Emin 70. Loops more than 35 cents out of tune after the shift are not outlined. With "Tempo from first loop" off, original keys are compared; with nothing playing, hovering works as before.
- The master loop's key is shown next to the BPM in the jam bar.

## 1.3

**Better "Only" detection**
- Vocals and pads are never taken from parts with a beat: a repeating kick is caught even at slow tempos (kick on beats 1 and 3), where the general kick limit used to let it through.
- Pads need a tone: crowd noise, applause, talk and wind without harmony are no longer "pads only".
- Pads with a melody on top come later in the queue than static ones.

**Order of loops with several "Only" types**
- The types take turns (for example pads, drums, pads, drums), starting with the type that has the cleanest part; inside a type clean parts come before "with extras". A type repeats in a row only when the others have nothing left. "Loops per record" stays the total for the record.
- "Only" now also works with 4-bar loops.

**Seams of pads and vocals**
- If a chord or a sung note starts slightly before the beat (soft attack, reverb), both loop boundaries move to the real start of the attack, so the attack no longer clicks at the end of the loop. The old tail fade, which itself caused a dip before the restart, is gone for these loops.
- Vocal loops whose loudness at the start and at the end differ a lot, and off-grid pads where something new comes in during the last half second, are used only when nothing else was found.

**Other**
- Years and BPM filters are off by default on the first start.
- Debugging mode (More settings): purity of every loop and a 👎 wrong match button that saves the loop and the analyzer's readings to a Feedback folder.
- All code comments and program messages are written in English (Russian and Spanish are translations); functions got explanatory docstrings. Behaviour of the unchanged parts was verified bit-for-bit against 1.2.2.

## 1.2.2
- Interface in English, Russian and Spanish (flags in the header).
- Floppy-disk button to save a loop's WAV when drag-and-drop doesn't work.
- "Stop" interrupts searching and downloading immediately.

## 1.2.1
- Seam check: loops no longer click at the end when the next hit starts slightly early.
- Dark filtered breaks (bass + kick + snare) are no longer taken as "bass only".

## 1.2
- Pipeline: downloads and analysis run in parallel (network strictly one request at a time).
- Lower memory use; stereo 24-bit only by default.

## 1.1
- "Only" bass / vocals / pads (several at once), type letter in file names.

## 1.0
- First version: search, download, beat-exact loops fitted to multiples of 5 BPM, key detection, favourites, re-run, ZIP for the Model:Samples.
