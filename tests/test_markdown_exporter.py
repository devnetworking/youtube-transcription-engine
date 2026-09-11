from src.exporters.blocks import group_by_chapter
from src.exporters.markdown_exporter import build_markdown
from src.models import AnalysisResult, Chapter, ProcessingReport, TranscriptSegment, VideoMetadata


def _metadata(**overrides):
    base = dict(
        video_id="abc123",
        url="https://www.youtube.com/watch?v=abc123",
        title="Zero Trust Architecture Explained",
        channel="Security Channel",
        publication_date="2024-01-15",
        duration_seconds=754,
        detected_language="en",
        transcription_source="Manual captions",
        processed_at="2024-01-16T00:00:00+00:00",
    )
    base.update(overrides)
    return VideoMetadata(**base)


def test_markdown_contains_title_and_video_information():
    metadata = _metadata()
    segments = [TranscriptSegment(start=0, end=2, text="Welcome to the show.")]
    sections = group_by_chapter(segments, [])
    md = build_markdown(metadata, sections, AnalysisResult(), ProcessingReport())

    assert md.startswith("# Zero Trust Architecture Explained")
    assert "## Video Information" in md
    assert "**URL:** https://www.youtube.com/watch?v=abc123" in md
    assert "**Transcription source:** Manual captions" in md


def test_markdown_full_transcript_section_has_timestamps():
    metadata = _metadata()
    segments = [
        TranscriptSegment(start=0, end=2, text="Introduction to the topic."),
        TranscriptSegment(start=80, end=82, text="Moving on to details."),
    ]
    sections = group_by_chapter(segments, [])
    md = build_markdown(metadata, sections, AnalysisResult(), ProcessingReport())

    assert "# Full Transcript" in md
    assert "[00:00:00]" in md
    assert "[00:01:20]" in md


def test_markdown_uses_provided_chapters():
    metadata = _metadata()
    segments = [
        TranscriptSegment(start=0, end=2, text="Intro text."),
        TranscriptSegment(start=300, end=302, text="Deep dive text."),
    ]
    chapters = [
        Chapter(index=1, title="Introduction", timestamp_seconds=0, source="youtube"),
        Chapter(index=2, title="Deep Dive", timestamp_seconds=300, source="youtube"),
    ]
    sections = group_by_chapter(segments, chapters)
    md = build_markdown(metadata, sections, AnalysisResult(), ProcessingReport())

    assert "## 1. Introduction" in md
    assert "## 2. Deep Dive" in md
    assert "1. `00:00:00` — Introduction" in md


def test_markdown_omits_empty_optional_sections():
    metadata = _metadata()
    segments = [TranscriptSegment(start=0, end=2, text="Just a short line.")]
    sections = group_by_chapter(segments, [])
    md = build_markdown(metadata, sections, AnalysisResult(), ProcessingReport())

    assert "## Mentioned Resources" not in md
    assert "## Questions or Research Leads" not in md


def test_markdown_renders_uncertain_marker():
    metadata = _metadata()
    segments = [TranscriptSegment(start=0, end=2, text="Something odd", uncertain=True, uncertain_reason="low_confidence")]
    sections = group_by_chapter(segments, [])
    md = build_markdown(metadata, sections, AnalysisResult(), ProcessingReport())

    assert "[uncertain: low_confidence]" in md
