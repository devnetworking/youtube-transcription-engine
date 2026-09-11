import pytest

from src.exceptions import MetadataFetchError
from src.pipeline import resolve_urls
from src.youtube import metadata


class _FakeYoutubeDL:
    def __init__(self, entries=None, raise_error=False):
        self._entries = entries or []
        self._raise_error = raise_error

    def __call__(self, opts):
        self._opts = opts
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=False):
        if self._raise_error:
            raise RuntimeError("network boom")
        return {"entries": self._entries}


def test_expand_playlist_returns_video_urls(monkeypatch):
    fake_ydl = _FakeYoutubeDL(entries=[{"id": "aaaaaaaaaaa"}, {"id": "bbbbbbbbbbb"}])

    class FakeYtDlpModule:
        YoutubeDL = fake_ydl

        class utils:
            class DownloadError(Exception):
                pass

    monkeypatch.setitem(__import__("sys").modules, "yt_dlp", FakeYtDlpModule)

    result = metadata.expand_playlist("https://www.youtube.com/playlist?list=PLxyz")
    assert result.urls == [
        "https://www.youtube.com/watch?v=aaaaaaaaaaa",
        "https://www.youtube.com/watch?v=bbbbbbbbbbb",
    ]
    assert result.truncated is False
    assert result.total_found == 2


def test_expand_playlist_caps_large_playlists(monkeypatch):
    entries = [{"id": f"vid{str(i).zfill(8)}"} for i in range(70)]
    fake_ydl = _FakeYoutubeDL(entries=entries)

    class FakeYtDlpModule:
        YoutubeDL = fake_ydl

        class utils:
            class DownloadError(Exception):
                pass

    monkeypatch.setitem(__import__("sys").modules, "yt_dlp", FakeYtDlpModule)

    result = metadata.expand_playlist("https://www.youtube.com/playlist?list=PLxyz")
    assert result.total_found == 70
    assert result.truncated is True
    assert len(result.urls) == metadata._MAX_PLAYLIST_VIDEOS


def test_expand_playlist_raises_on_failure(monkeypatch):
    fake_ydl = _FakeYoutubeDL(raise_error=True)

    class FakeYtDlpModule:
        YoutubeDL = fake_ydl

        class utils:
            class DownloadError(Exception):
                pass

    monkeypatch.setitem(__import__("sys").modules, "yt_dlp", FakeYtDlpModule)

    with pytest.raises(MetadataFetchError):
        metadata.expand_playlist("https://www.youtube.com/playlist?list=PLxyz")


def test_resolve_urls_passes_through_plain_video_urls():
    urls = ["https://www.youtube.com/watch?v=aaaaaaaaaaa"]
    assert resolve_urls(urls) == urls


def test_resolve_urls_expands_playlist(monkeypatch):
    from src import pipeline as pipeline_module
    from src.youtube.metadata import PlaylistExpansion

    monkeypatch.setattr(
        pipeline_module,
        "expand_playlist",
        lambda url, verbose=False: PlaylistExpansion(
            urls=["https://www.youtube.com/watch?v=aaaaaaaaaaa"],
            truncated=False,
            total_found=1,
        ),
    )

    messages = []
    result = resolve_urls(
        ["https://www.youtube.com/playlist?list=PLxyz"],
        report=lambda msg, level: messages.append((msg, level)),
    )

    assert result == ["https://www.youtube.com/watch?v=aaaaaaaaaaa"]
    assert any("expanded" in msg.lower() for msg, _level in messages)


def test_resolve_urls_reports_error_and_continues(monkeypatch):
    from src import pipeline as pipeline_module

    def raise_error(url, verbose=False):
        raise MetadataFetchError("boom")

    monkeypatch.setattr(pipeline_module, "expand_playlist", raise_error)

    messages = []
    result = resolve_urls(
        ["https://www.youtube.com/playlist?list=PLxyz", "https://www.youtube.com/watch?v=aaaaaaaaaaa"],
        report=lambda msg, level: messages.append((msg, level)),
    )

    assert result == ["https://www.youtube.com/watch?v=aaaaaaaaaaa"]
    assert any(level == "error" for _msg, level in messages)
