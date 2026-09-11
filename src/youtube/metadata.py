"""YouTube URL normalization and metadata retrieval (spec sections 2 and 13)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ..exceptions import (
    AgeRestrictedError,
    InvalidURLError,
    MetadataFetchError,
    NetworkError,
    PrivateVideoError,
    VideoUnavailableError,
)
from ..models import VideoMetadata

class SilentYtDlpLogger:
    """Swallows yt-dlp's own log lines; we surface errors via our own
    typed exceptions and messages instead (spec section 20: no noisy
    low-level logs unless verbose mode is on).

    When `verbose` is set, warnings/errors are forwarded to `sink`
    instead of being swallowed, so --verbose actually surfaces yt-dlp's
    own diagnostics rather than being a no-op flag."""

    def __init__(self, verbose: bool = False, sink: Optional[Callable[[str], None]] = None):
        self._verbose = verbose
        self._sink = sink or (lambda _msg: None)

    def debug(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        if self._verbose:
            self._sink(f"yt-dlp: {msg}")

    def error(self, msg: str) -> None:
        if self._verbose:
            self._sink(f"yt-dlp: {msg}")


_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

_URL_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})"),
    re.compile(r"(?:youtu\.be/)([A-Za-z0-9_-]{11})"),
    re.compile(r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})"),
    re.compile(r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})"),
    re.compile(r"(?:youtube\.com/live/)([A-Za-z0-9_-]{11})"),
]


def extract_video_id(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise InvalidURLError("Empty URL.")

    if _VIDEO_ID_RE.match(url):
        return url  # Already a bare video ID.

    for pattern in _URL_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)

    raise InvalidURLError(f"Could not parse a YouTube video ID from: {url!r}")


def normalize_url(url: str) -> str:
    """Return the canonical `https://www.youtube.com/watch?v=<id>` form."""
    video_id = extract_video_id(url)
    return f"https://www.youtube.com/watch?v={video_id}"


def is_playlist_url(url: str) -> bool:
    return "list=" in (url or "") and "watch?v=" not in (url or "")


_MAX_PLAYLIST_VIDEOS = 50


class PlaylistExpansion:
    def __init__(self, urls: list[str], truncated: bool, total_found: int):
        self.urls = urls
        self.truncated = truncated
        self.total_found = total_found


def expand_playlist(url: str, verbose: bool = False) -> PlaylistExpansion:
    """Resolve a playlist URL into its individual video URLs.

    Uses yt-dlp's flat extraction (listing only, no per-video metadata
    fetch) so this stays fast even for a fairly large playlist. Capped
    at `_MAX_PLAYLIST_VIDEOS` so pasting a huge playlist can't silently
    kick off hundreds of downloads/transcriptions.
    """
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover
        raise MetadataFetchError("yt-dlp is not installed.") from exc

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "logger": SilentYtDlpLogger(verbose=verbose),
        "color": "no_color",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001
        raise MetadataFetchError(f"Failed to expand playlist {url}: {exc}") from exc

    entries = (info or {}).get("entries") or []
    video_ids = [e["id"] for e in entries if e.get("id")]

    if not video_ids:
        raise MetadataFetchError(f"Playlist has no videos or could not be read: {url}")

    total_found = len(video_ids)
    truncated = total_found > _MAX_PLAYLIST_VIDEOS
    video_ids = video_ids[:_MAX_PLAYLIST_VIDEOS]

    return PlaylistExpansion(
        urls=[f"https://www.youtube.com/watch?v={vid}" for vid in video_ids],
        truncated=truncated,
        total_found=total_found,
    )


def fetch_metadata(
    url: str,
    verbose: bool = False,
    report: Optional[Callable[[str], None]] = None,
) -> tuple[VideoMetadata, dict[str, Any]]:
    """Fetch video metadata via yt-dlp without downloading media.

    Returns (VideoMetadata, raw_info_dict). The raw dict is kept around
    for downstream use (e.g. yt-dlp's own 'chapters' and
    'automatic_captions'/'subtitles' fields) so we don't hit the network
    twice for the same video.
    """
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover - exercised via mocks in tests
        raise MetadataFetchError("yt-dlp is not installed.") from exc

    canonical_url = normalize_url(url)
    video_id = extract_video_id(url)

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "logger": SilentYtDlpLogger(verbose=verbose, sink=report),
        "color": "no_color",
        # The default "web" client increasingly needs a JS runtime to pass
        # YouTube's anti-bot signature challenge and can misreport a
        # perfectly available video as unavailable. "android" sidesteps
        # that; "web" stays as a fallback for anything android can't see.
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(canonical_url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        message = str(exc).lower()
        if "private" in message:
            raise PrivateVideoError(f"Video is private: {canonical_url}") from exc
        if "age" in message and "restrict" in message:
            raise AgeRestrictedError(f"Video is age-restricted: {canonical_url}") from exc
        if "unavailable" in message or "removed" in message:
            raise VideoUnavailableError(f"Video is unavailable: {canonical_url}") from exc
        if "network" in message or "urlopen" in message or "timed out" in message:
            raise NetworkError(f"Network failure fetching {canonical_url}: {exc}") from exc
        raise MetadataFetchError(f"yt-dlp failed for {canonical_url}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - normalize any other yt-dlp failure
        raise MetadataFetchError(f"yt-dlp failed for {canonical_url}: {exc}") from exc

    if not info:
        raise MetadataFetchError(f"yt-dlp returned no data for {canonical_url}")

    metadata = VideoMetadata(
        video_id=info.get("id", video_id),
        url=canonical_url,
        title=info.get("title"),
        channel=info.get("channel") or info.get("uploader"),
        channel_url=info.get("channel_url") or info.get("uploader_url"),
        publication_date=_format_upload_date(info.get("upload_date")),
        duration_seconds=info.get("duration"),
        processed_at=datetime.now(timezone.utc).isoformat(),
    )
    return metadata, info


def _format_upload_date(raw: Optional[str]) -> Optional[str]:
    if not raw or len(raw) != 8:
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d").date().isoformat()
    except ValueError:
        return None
