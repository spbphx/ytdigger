"""Shorts search compatibility for YouTube's gridShelfViewModel results."""
from itertools import chain
from urllib.parse import parse_qs, urlparse

from yt_dlp.extractor.youtube import YoutubeSearchURLIE
from yt_dlp.utils import traverse_obj


class YoutubeShortsSearchIE(YoutubeSearchURLIE):
    """Read the filtered page first: the generic search API can return an empty page.

    yt-dlp still owns HTTP, cookies, metadata parsing and continuation requests.
    Only register this extractor on the downloader used for a Shorts search.
    """

    def _shorts_models(self, value):
        if isinstance(value, dict):
            if "shortsLockupViewModel" in value:
                yield from self._rich_entries({"content": value})
                return
            for child in value.values():
                yield from self._shorts_models(child)
        elif isinstance(value, list):
            for child in value:
                yield from self._shorts_models(child)

    def _shorts_entries(self, url, query):
        webpage = self._download_webpage(url, query)
        data = self.extract_yt_initial_data(query, webpage)
        ytcfg = self.extract_ytcfg(query, webpage)
        parent = traverse_obj(data, (
            "contents", "twoColumnSearchResultsRenderer", "primaryContents", "sectionListRenderer")) or {}
        seen, tokens = set(), set()
        page = 1
        while parent:
            continuation = [None]
            # Retain support for older reel/video renderers alongside the new grid shelves.
            for entry in chain(self._extract_entries(parent, continuation), self._shorts_models(parent)):
                vid = entry.get("id")
                if vid and vid not in seen and "/shorts/" in (entry.get("url") or ""):
                    seen.add(vid)
                    yield entry
            next_page = continuation[0] or self._extract_continuation(parent)
            token = (next_page or {}).get("continuation")
            if not token or token in tokens:
                break
            tokens.add(token)
            page += 1
            headers = self.generate_api_headers(
                ytcfg=ytcfg, visitor_data=self._extract_visitor_data(data), default_client="web")
            data = self._extract_response(
                item_id=query, ep="search", query=next_page, ytcfg=ytcfg, headers=headers,
                note=f"Downloading Shorts results page {page}",
                check_get_keys=("onResponseReceivedCommands", "onResponseReceivedActions", "continuationContents"))
            contents = traverse_obj(data, (
                ("onResponseReceivedCommands", "onResponseReceivedActions"), ...,
                "appendContinuationItemsAction", "continuationItems"), get_all=False)
            parent = {"contents": contents} if contents else traverse_obj(
                data, ("continuationContents", "sectionListContinuation")) or {}

    def _real_extract(self, url):
        query = parse_qs(urlparse(url).query)["search_query"][0]
        return self.playlist_result(self._shorts_entries(url, query), query, query)
