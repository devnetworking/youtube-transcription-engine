from datetime import datetime, timedelta, timezone

from src.documents.cleanup import run_retention_cleanup
from src.documents.config import DocumentSettings
from src.documents.models import DocumentJob, DocumentOutput, JobOperation, JobStatus, OutputType
from src.documents.repository import DocumentRepository
from src.documents.storage import OUTPUTS, LocalStorageProvider


def _old_iso(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _make_job_with_output(repo, storage, job_id, completed_at):
    job = DocumentJob(
        id=job_id, operation=JobOperation.MERGE, status=JobStatus.COMPLETED,
        input_document_ids=["doc1"], created_at=completed_at, completed_at=completed_at,
    )
    repo.create_job(job)
    key = storage.write_bytes(OUTPUTS, job_id, "result.pdf", b"%PDF-1.4 fake")
    repo.create_output(DocumentOutput(
        id=f"{job_id}-out", job_id=job_id, output_type=OutputType.PDF, storage_key=key,
        filename="result.pdf", file_size=10, created_at=completed_at,
    ))
    return job


def test_cleanup_removes_job_outputs_past_retention(tmp_path):
    storage = LocalStorageProvider(tmp_path)
    repo = DocumentRepository(tmp_path / "db.sqlite3")
    _make_job_with_output(repo, storage, "old-job", _old_iso(40))

    settings = DocumentSettings(output_retention_days=30, temp_file_retention_hours=0)
    run_retention_cleanup(repo, storage, settings)

    assert repo.get_job("old-job") is None
    assert not storage.exists(f"{OUTPUTS}/old-job/result.pdf")


def test_cleanup_keeps_recent_job_outputs(tmp_path):
    storage = LocalStorageProvider(tmp_path)
    repo = DocumentRepository(tmp_path / "db.sqlite3")
    _make_job_with_output(repo, storage, "recent-job", _old_iso(1))

    settings = DocumentSettings(output_retention_days=30, temp_file_retention_hours=0)
    run_retention_cleanup(repo, storage, settings)

    assert repo.get_job("recent-job") is not None
    assert storage.exists(f"{OUTPUTS}/recent-job/result.pdf")


def test_cleanup_ignores_jobs_still_processing(tmp_path):
    storage = LocalStorageProvider(tmp_path)
    repo = DocumentRepository(tmp_path / "db.sqlite3")
    job = DocumentJob(
        id="active-job", operation=JobOperation.SPLIT, status=JobStatus.PROCESSING,
        input_document_ids=["doc1"], created_at=_old_iso(90),
    )
    repo.create_job(job)

    settings = DocumentSettings(output_retention_days=30, temp_file_retention_hours=0)
    run_retention_cleanup(repo, storage, settings)

    assert repo.get_job("active-job") is not None


def test_cleanup_disabled_with_zero_retention(tmp_path):
    storage = LocalStorageProvider(tmp_path)
    repo = DocumentRepository(tmp_path / "db.sqlite3")
    _make_job_with_output(repo, storage, "old-job", _old_iso(400))

    settings = DocumentSettings(output_retention_days=0, temp_file_retention_hours=0)
    run_retention_cleanup(repo, storage, settings)

    assert repo.get_job("old-job") is not None


def test_cleanup_removes_stale_tmp_directories(tmp_path):
    import os
    import time

    storage = LocalStorageProvider(tmp_path)
    repo = DocumentRepository(tmp_path / "db.sqlite3")
    stale_dir = storage.scratch_dir("stale-job")
    old_time = time.time() - 3600 * 48
    os.utime(stale_dir, (old_time, old_time))

    settings = DocumentSettings(output_retention_days=0, temp_file_retention_hours=24)
    run_retention_cleanup(repo, storage, settings)

    assert not stale_dir.exists()
