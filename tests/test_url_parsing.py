import pytest

from src.exceptions import InvalidURLError
from src.youtube.metadata import extract_video_id, is_playlist_url, normalize_url


@pytest.mark.parametrize(
    "url,expected_id",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_extract_video_id(url, expected_id):
    assert extract_video_id(url) == expected_id


def test_normalize_url_canonical_form():
    assert normalize_url("https://youtu.be/dQw4w9WgXcQ") == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_extract_video_id_invalid_raises():
    with pytest.raises(InvalidURLError):
        extract_video_id("https://example.com/not-a-video")


def test_extract_video_id_empty_raises():
    with pytest.raises(InvalidURLError):
        extract_video_id("")


def test_is_playlist_url():
    assert is_playlist_url("https://www.youtube.com/playlist?list=PLxyz")
    assert not is_playlist_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
