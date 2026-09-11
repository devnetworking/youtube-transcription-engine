from src.exporters.blocks import group_by_chapter
from src.exporters.text_exporter import build_text
from src.models import TranscriptSegment, VideoMetadata


def test_text_exporter_has_no_markdown_syntax():
    metadata = VideoMetadata(title="Sample Video", url="https://youtu.be/abc123", channel="Chan", detected_language="en")
    segments = [TranscriptSegment(start=0, end=2, text="Hello world.")]
    sections = group_by_chapter(segments, [])
    txt = build_text(metadata, sections)

    assert "#" not in txt
    assert "**" not in txt
    assert "|---" not in txt


def test_text_exporter_structure():
    metadata = VideoMetadata(title="Sample Video", url="https://youtu.be/abc123", channel="Chan", detected_language="en")
    segments = [TranscriptSegment(start=0, end=2, text="Hello world.")]
    sections = group_by_chapter(segments, [])
    txt = build_text(metadata, sections)

    assert txt.startswith("Sample Video\nURL: https://youtu.be/abc123")
    assert "TRANSCRIPT" in txt
    assert "[00:00:00] Hello world." in txt
    assert txt.strip().endswith("END OF TRANSCRIPT\n==================================================")
