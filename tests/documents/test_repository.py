from src.documents.models import Document, DocumentJob, DocumentStatus, JobOperation, JobStatus, PipelineStage
from src.documents.repository import DocumentRepository, now_iso


def _document(doc_id="doc1") -> Document:
    return Document(
        id=doc_id, original_name="a.pdf", storage_key=f"uploads/{doc_id}/original.pdf",
        mime_type="application/pdf", file_size=100, page_count=5,
        checksum_sha256="abc", status=DocumentStatus.READY, created_at=now_iso(),
    )


def test_create_and_get_document(tmp_path):
    repo = DocumentRepository(tmp_path / "db.sqlite3")
    repo.create_document(_document())
    fetched = repo.get_document("doc1")
    assert fetched is not None
    assert fetched.original_name == "a.pdf"
    assert fetched.page_count == 5


def test_soft_delete_hides_document_from_listing(tmp_path):
    repo = DocumentRepository(tmp_path / "db.sqlite3")
    repo.create_document(_document())
    repo.soft_delete_document("doc1")
    assert repo.get_document("doc1").status == DocumentStatus.DELETED
    assert repo.list_documents() == []


def test_find_by_checksum_only_matches_ready_documents(tmp_path):
    repo = DocumentRepository(tmp_path / "db.sqlite3")
    repo.create_document(_document())
    assert repo.find_by_checksum("abc") is not None
    repo.soft_delete_document("doc1")
    assert repo.find_by_checksum("abc") is None


def test_job_lifecycle_updates_progress_and_status(tmp_path):
    repo = DocumentRepository(tmp_path / "db.sqlite3")
    job = DocumentJob(
        id="job1", operation=JobOperation.MERGE, stages=[PipelineStage(key="merge", label="Merging")],
        input_document_ids=["doc1"], created_at=now_iso(),
    )
    repo.create_job(job)
    repo.update_job("job1", status=JobStatus.PROCESSING, progress=0.5, stage="merge")
    fetched = repo.get_job("job1")
    assert fetched.status == JobStatus.PROCESSING
    assert fetched.progress == 0.5
    assert fetched.stage == "merge"


def test_reset_job_for_retry_clears_previous_failure(tmp_path):
    repo = DocumentRepository(tmp_path / "db.sqlite3")
    job = DocumentJob(id="job1", operation=JobOperation.SPLIT, input_document_ids=["doc1"], created_at=now_iso())
    repo.create_job(job)
    repo.update_job("job1", status=JobStatus.FAILED, error_message="boom", error_code="processing_error")
    repo.reset_job_for_retry("job1")
    fetched = repo.get_job("job1")
    assert fetched.status == JobStatus.QUEUED
    assert fetched.error_message is None
    assert fetched.error_code is None


def test_cancel_request_flag(tmp_path):
    repo = DocumentRepository(tmp_path / "db.sqlite3")
    job = DocumentJob(id="job1", operation=JobOperation.SPLIT, input_document_ids=["doc1"], created_at=now_iso())
    repo.create_job(job)
    assert not repo.is_cancel_requested("job1")
    repo.request_cancel("job1")
    assert repo.is_cancel_requested("job1")


def test_delete_job_cascades_to_outputs(tmp_path):
    from src.documents.models import DocumentOutput, OutputType

    repo = DocumentRepository(tmp_path / "db.sqlite3")
    job = DocumentJob(id="job1", operation=JobOperation.MERGE, input_document_ids=["doc1"], created_at=now_iso())
    repo.create_job(job)
    repo.create_output(DocumentOutput(
        id="out1", job_id="job1", output_type=OutputType.PDF, storage_key="outputs/job1/x.pdf",
        filename="x.pdf", file_size=10, created_at=now_iso(),
    ))
    repo.delete_job("job1")
    assert repo.get_job("job1") is None
    assert repo.list_outputs("job1") == []
