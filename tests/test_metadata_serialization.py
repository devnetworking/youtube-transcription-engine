import json

from src.exporters.json_exporter import write_metadata, write_processing_report
from src.models import ProcessingReport, QualityLevel, VideoMetadata


def test_metadata_serializes_expected_fields(tmp_path):
    metadata = VideoMetadata(
        video_id="abc123",
        url="https://www.youtube.com/watch?v=abc123",
        title="A Video",
        channel="A Channel",
        publication_date="2024-01-01",
        duration_seconds=120,
        detected_language="en",
        transcription_source="Manual captions",
        processed_at="2024-01-02T00:00:00+00:00",
        word_count=42,
        chapter_count=2,
    )
    path = tmp_path / "metadata.json"
    write_metadata(path, metadata)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["video_id"] == "abc123"
    assert data["word_count"] == 42
    assert data["chapter_count"] == 2


def test_metadata_missing_fields_are_null_not_fabricated(tmp_path):
    metadata = VideoMetadata(video_id="abc123", url="https://www.youtube.com/watch?v=abc123")
    path = tmp_path / "metadata.json"
    write_metadata(path, metadata)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["channel"] is None
    assert data["publication_date"] is None
    assert data["duration_seconds"] is None


def test_processing_report_round_trips(tmp_path):
    report = ProcessingReport(status="success", caption_source_found=True, uncertain_segments=3, quality=QualityLevel.MEDIUM)
    path = tmp_path / "processing_report.json"
    write_processing_report(path, report)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["status"] == "success"
    assert data["quality"] == "MEDIUM"
    assert data["uncertain_segments"] == 3
