from src.analysis.chapters import chapters_from_youtube, infer_chapters
from src.models import TranscriptSegment


def test_chapters_from_youtube_maps_fields():
    raw = [
        {"title": "Intro", "start_time": 0},
        {"title": "Deep Dive", "start_time": 120},
    ]
    chapters = chapters_from_youtube(raw)
    assert [c.title for c in chapters] == ["Intro", "Deep Dive"]
    assert chapters[0].source == "youtube"
    assert chapters[1].timestamp_seconds == 120


def test_chapters_from_youtube_handles_none():
    assert chapters_from_youtube(None) == []


def test_infer_chapters_short_video_returns_single_chapter():
    segments = [TranscriptSegment(start=0, end=30, text="short video content")]
    chapters = infer_chapters(segments)
    assert len(chapters) == 1
    assert chapters[0].timestamp_seconds == 0.0


def test_infer_chapters_long_video_produces_multiple_windows():
    segments = [
        TranscriptSegment(start=i * 60, end=i * 60 + 55, text=f"topic segment number {i} about machine learning models")
        for i in range(20)
    ]
    chapters = infer_chapters(segments)
    assert len(chapters) > 1
    # Chapters should be ordered and not fragmented every few seconds.
    for prev, curr in zip(chapters, chapters[1:]):
        assert curr.timestamp_seconds > prev.timestamp_seconds
