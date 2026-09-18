"""YouTube Transcript as a Documents job. Everything that touches the
network (yt-dlp, youtube-transcript-api, Whisper) is monkeypatched at
the exact names youtube_transcript_service.py imported, matching this
project's existing convention (see tests/test_*.py for the YouTube
tool itself) - no test here makes a real network call.
"""

from __future__ import annotations

import pytest

from src.documents.config import DocumentSettings
from src.documents.exceptions import YouTubeError
from src.documents.models import DocumentSource, JobStatus, OutputType, YouTubeTranscriptOptions
from src.documents.repository import DocumentRepository
from src.documents.services import youtube_transcript_service as svc_module
from src.documents.services.youtube_transcript_service import YouTubeTranscriptService
from src.documents.storage import LocalStorageProvider
from src.exceptions import PrivateVideoError
from src.models import QualityLevel, VideoMetadata, VideoOutcome


@pytest.fixture
def service(tmp_path):
    storage = LocalStorageProvider(tmp_path)
    repository = DocumentRepository(tmp_path / "db.sqlite3")
    settings = DocumentSettings()
    return YouTubeTranscriptService(storage, repository, settings), repository, storage


def test_preview_rejects_invalid_url(service):
    svc, _, _ = service
    with pytest.raises(YouTubeError) as exc_info:
        svc.preview("not a youtube url at all")
    assert exc_info.value.code == "YT_INVALID_URL"


def test_preview_maps_private_video_to_human_message(service, monkeypatch):
    svc, _, _ = service

    def fake_fetch_metadata(url, **kwargs):
        raise PrivateVideoError("Video is private: whatever")

    monkeypatch.setattr(svc_module, "fetch_metadata", fake_fetch_metadata)
    with pytest.raises(YouTubeError) as exc_info:
        svc.preview("https://www.youtube.com/watch?v=abcdefghijk")
    assert exc_info.value.code == "YT_PRIVATE_VIDEO"
    assert "private" in str(exc_info.value).lower()
    assert "Traceback" not in str(exc_info.value)


def test_preview_returns_metadata_and_languages(service, monkeypatch):
    svc, _, _ = service

    def fake_fetch_metadata(url, **kwargs):
        metadata = VideoMetadata(
            video_id="abcdefghijk", url=url, title="A Talk", channel="A Channel",
            duration_seconds=125, publication_date="2024-01-01",
        )
        return metadata, {"thumbnail": "https://img.example/thumb.jpg"}

    monkeypatch.setattr(svc_module, "fetch_metadata", fake_fetch_metadata)
    monkeypatch.setattr(svc_module, "list_available_languages", lambda video_id: [
        {"code": "en", "name": "English", "is_generated": False},
    ])

    preview = svc.preview("https://www.youtube.com/watch?v=abcdefghijk")
    assert preview["title"] == "A Talk"
    assert preview["channel"] == "A Channel"
    assert preview["captions_available"] is True
    assert preview["languages"][0]["code"] == "en"
    assert preview["thumbnail"] == "https://img.example/thumb.jpg"
    assert preview["is_playlist"] is False


def test_preview_playlist_reports_video_count(service, monkeypatch):
    svc, _, _ = service

    class FakeExpansion:
        urls = ["https://www.youtube.com/watch?v=aaaaaaaaaaa", "https://www.youtube.com/watch?v=bbbbbbbbbbb"]
        truncated = False
        total_found = 2

    monkeypatch.setattr(svc_module, "expand_playlist", lambda url, **kwargs: FakeExpansion())
    preview = svc.preview("https://www.youtube.com/playlist?list=PLxyz")
    assert preview["is_playlist"] is True
    assert preview["video_count"] == 2


def test_create_jobs_expands_into_one_job_per_video(service, monkeypatch):
    svc, repository, _ = service
    monkeypatch.setattr(svc_module, "resolve_urls", lambda urls: [
        "https://www.youtube.com/watch?v=aaaaaaaaaaa", "https://www.youtube.com/watch?v=bbbbbbbbbbb",
    ])
    jobs = svc.create_jobs(YouTubeTranscriptOptions(url="https://www.youtube.com/playlist?list=PLxyz"))
    assert len(jobs) == 2
    assert all(j.status == JobStatus.QUEUED for j in jobs)
    assert repository.get_job(jobs[0].id) is not None
    assert jobs[0].options["url"] != jobs[1].options["url"]


def test_create_jobs_raises_when_nothing_resolves(service, monkeypatch):
    svc, _, _ = service
    monkeypatch.setattr(svc_module, "resolve_urls", lambda urls: [])
    with pytest.raises(YouTubeError):
        svc.create_jobs(YouTubeTranscriptOptions(url="https://www.youtube.com/watch?v=abcdefghijk"))


class _FakeToken:
    def check(self):
        pass

    def set_stage(self, *args, **kwargs):
        pass

    def finish_stages(self, *args, **kwargs):
        pass


def test_build_target_registers_outputs_and_document(service, monkeypatch, tmp_path):
    svc, repository, storage = service
    monkeypatch.setattr(svc_module, "resolve_urls", lambda urls: [urls[0]])
    job = svc.create_jobs(YouTubeTranscriptOptions(url="https://www.youtube.com/watch?v=abcdefghijk"))[0]

    def fake_process_video(url, config, output_root, report=None):
        report("[1/6] Reading YouTube metadata...", "step")
        report("[6/6] Writing transcript.md and transcript.txt...", "step")
        video_dir = output_root / "A_Talk"
        video_dir.mkdir(parents=True, exist_ok=True)
        (video_dir / "transcript.md").write_text("# A Talk\n\nHello world.\n", encoding="utf-8")
        (video_dir / "transcript.txt").write_text("A Talk\n\nHello world.\n", encoding="utf-8")
        (video_dir / "metadata.json").write_text("{}", encoding="utf-8")
        return VideoOutcome(success=True, video_dir=str(video_dir), title="A Talk", quality=QualityLevel.HIGH, source="Manual captions")

    monkeypatch.setattr(svc_module, "process_video", fake_process_video)

    target = svc.build_target(job)
    target(_FakeToken())

    outputs = repository.list_outputs(job.id)
    filenames = {o.filename for o in outputs}
    assert "transcript.md" in filenames
    assert "transcript.txt" in filenames
    assert "package.zip" in filenames

    md_output = next(o for o in outputs if o.output_type == OutputType.MARKDOWN)
    assert storage.exists(md_output.storage_key)

    documents = repository.list_documents()
    assert len(documents) == 1
    assert documents[0].source == DocumentSource.YOUTUBE
    assert documents[0].source_job_id == job.id
    assert documents[0].mime_type == "text/markdown"

    updated_job = repository.get_job(job.id)
    assert updated_job.result_summary["title"] == "A Talk"


def test_build_target_raises_on_pipeline_failure(service, monkeypatch):
    svc, _, _ = service
    monkeypatch.setattr(svc_module, "resolve_urls", lambda urls: [urls[0]])
    job = svc.create_jobs(YouTubeTranscriptOptions(url="https://www.youtube.com/watch?v=abcdefghijk"))[0]

    def fake_process_video(url, config, output_root, report=None):
        return VideoOutcome(success=False, errors=["Captions unavailable and Whisper is not installed."])

    monkeypatch.setattr(svc_module, "process_video", fake_process_video)
    target = svc.build_target(job)
    with pytest.raises(Exception, match="Whisper is not installed"):
        target(_FakeToken())
