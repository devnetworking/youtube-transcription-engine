"""Database access for documents, jobs and outputs.

One class wrapping short-lived SQLite connections (db.py) behind the
Pydantic models in models.py, so every other module (services, routes)
works with typed objects and never sees a raw sqlite3.Row or writes SQL
itself.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import db as db_module
from .models import (
    Document,
    DocumentJob,
    DocumentOutput,
    DocumentSource,
    DocumentStatus,
    JobOperation,
    JobStatus,
    LogEntry,
    OutputType,
    PipelineStage,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_document(row: sqlite3.Row) -> Document:
    return Document(
        id=row["id"],
        original_name=row["original_name"],
        storage_key=row["storage_key"],
        mime_type=row["mime_type"],
        file_size=row["file_size"],
        page_count=row["page_count"],
        checksum_sha256=row["checksum_sha256"],
        status=DocumentStatus(row["status"]),
        source=DocumentSource(row["source"]),
        source_job_id=row["source_job_id"],
        error_message=row["error_message"],
        created_at=row["created_at"],
        deleted_at=row["deleted_at"],
    )


def _row_to_job(row: sqlite3.Row) -> DocumentJob:
    return DocumentJob(
        id=row["id"],
        operation=JobOperation(row["operation"]),
        status=JobStatus(row["status"]),
        progress=row["progress"],
        stage=row["stage"],
        stages=[PipelineStage(**s) for s in json.loads(row["stages_json"])],
        logs=[LogEntry(**entry) for entry in json.loads(row["logs_json"])],
        input_document_ids=json.loads(row["input_document_ids_json"]),
        options=json.loads(row["options_json"]),
        error_code=row["error_code"],
        error_message=row["error_message"],
        result_summary=json.loads(row["result_summary_json"]),
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def _row_to_output(row: sqlite3.Row) -> DocumentOutput:
    return DocumentOutput(
        id=row["id"],
        job_id=row["job_id"],
        output_type=OutputType(row["output_type"]),
        storage_key=row["storage_key"],
        filename=row["filename"],
        file_size=row["file_size"],
        created_at=row["created_at"],
    )


class DocumentRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_module.init_db(db_path)

    # -- documents ---------------------------------------------------

    def create_document(self, document: Document) -> None:
        with db_module.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO documents
                   (id, original_name, storage_key, mime_type, file_size, page_count,
                    checksum_sha256, status, source, source_job_id, error_message, created_at, deleted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    document.id, document.original_name, document.storage_key, document.mime_type,
                    document.file_size, document.page_count, document.checksum_sha256,
                    document.status.value, document.source.value, document.source_job_id,
                    document.error_message, document.created_at, document.deleted_at,
                ),
            )

    def get_document(self, document_id: str) -> Optional[Document]:
        with db_module.connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        return _row_to_document(row) if row else None

    def find_by_checksum(self, checksum: str) -> Optional[Document]:
        with db_module.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE checksum_sha256 = ? AND status = 'ready' "
                "ORDER BY created_at DESC LIMIT 1",
                (checksum,),
            ).fetchone()
        return _row_to_document(row) if row else None

    def list_documents(
        self, search: Optional[str] = None, limit: int = 50, offset: int = 0, include_deleted: bool = False
    ) -> list[Document]:
        query = "SELECT * FROM documents WHERE 1=1"
        params: list = []
        if not include_deleted:
            query += " AND status != 'deleted'"
        if search:
            query += " AND original_name LIKE ?"
            params.append(f"%{search}%")
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with db_module.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_document(r) for r in rows]

    def count_documents(self, include_deleted: bool = False) -> int:
        query = "SELECT COUNT(*) FROM documents"
        if not include_deleted:
            query += " WHERE status != 'deleted'"
        with db_module.connect(self.db_path) as conn:
            return conn.execute(query).fetchone()[0]

    def update_document_status(
        self, document_id: str, status: DocumentStatus, error_message: Optional[str] = None,
        page_count: Optional[int] = None,
    ) -> None:
        with db_module.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE documents SET status = ?, error_message = COALESCE(?, error_message), "
                "page_count = COALESCE(?, page_count) WHERE id = ?",
                (status.value, error_message, page_count, document_id),
            )

    def rename_document(self, document_id: str, new_name: str) -> None:
        with db_module.connect(self.db_path) as conn:
            conn.execute("UPDATE documents SET original_name = ? WHERE id = ?", (new_name, document_id))

    def soft_delete_document(self, document_id: str) -> None:
        with db_module.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE documents SET status = 'deleted', deleted_at = ? WHERE id = ?",
                (now_iso(), document_id),
            )

    # -- jobs ----------------------------------------------------------

    def create_job(self, job: DocumentJob) -> None:
        with db_module.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO document_jobs
                   (id, operation, status, progress, stage, stages_json, logs_json, input_document_ids_json,
                    options_json, error_code, error_message, result_summary_json, created_at,
                    started_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job.id, job.operation.value, job.status.value, job.progress, job.stage,
                    json.dumps([s.model_dump() for s in job.stages]),
                    json.dumps([entry.model_dump() for entry in job.logs]),
                    json.dumps(job.input_document_ids), json.dumps(job.options),
                    job.error_code, job.error_message, json.dumps(job.result_summary),
                    job.created_at, job.started_at, job.completed_at,
                ),
            )

    def append_job_log(self, job_id: str, message: str, level: str = "info") -> None:
        """Raw progress log (distinct from the named PipelineStage list):
        gives the Job Details view the same scrolling log the original
        YouTube tool's UI had, without needing named stages for every
        message an operation wants to surface."""
        with db_module.connect(self.db_path) as conn:
            row = conn.execute("SELECT logs_json FROM document_jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return
            logs = json.loads(row["logs_json"])
            logs.append({"message": message, "level": level, "at": now_iso()})
            conn.execute("UPDATE document_jobs SET logs_json = ? WHERE id = ?", (json.dumps(logs), job_id))

    def get_job(self, job_id: str) -> Optional[DocumentJob]:
        with db_module.connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM document_jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None

    def list_jobs(
        self, status: Optional[str] = None, operation: Optional[str] = None,
        limit: int = 50, offset: int = 0,
    ) -> list[DocumentJob]:
        query = "SELECT * FROM document_jobs WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if operation:
            query += " AND operation = ?"
            params.append(operation)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with db_module.connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_job(r) for r in rows]

    def jobs_for_document(self, document_id: str) -> list[DocumentJob]:
        with db_module.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM document_jobs WHERE input_document_ids_json LIKE ? ORDER BY created_at DESC",
                (f'%"{document_id}"%',),
            ).fetchall()
        return [_row_to_job(r) for r in rows]

    def update_job(
        self,
        job_id: str,
        status: Optional[JobStatus] = None,
        progress: Optional[float] = None,
        stage: Optional[str] = None,
        stages: Optional[list[PipelineStage]] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        result_summary: Optional[dict] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> None:
        fields, params = [], []
        if status is not None:
            fields.append("status = ?"); params.append(status.value)
        if progress is not None:
            fields.append("progress = ?"); params.append(progress)
        if stage is not None:
            fields.append("stage = ?"); params.append(stage)
        if stages is not None:
            fields.append("stages_json = ?"); params.append(json.dumps([s.model_dump() for s in stages]))
        if error_code is not None:
            fields.append("error_code = ?"); params.append(error_code)
        if error_message is not None:
            fields.append("error_message = ?"); params.append(error_message)
        if result_summary is not None:
            fields.append("result_summary_json = ?"); params.append(json.dumps(result_summary))
        if started_at is not None:
            fields.append("started_at = ?"); params.append(started_at)
        if completed_at is not None:
            fields.append("completed_at = ?"); params.append(completed_at)
        if not fields:
            return
        params.append(job_id)
        with db_module.connect(self.db_path) as conn:
            conn.execute(f"UPDATE document_jobs SET {', '.join(fields)} WHERE id = ?", params)

    def reset_job_for_retry(self, job_id: str) -> None:
        """Unlike update_job() (where None means "leave unchanged"), a
        retry must explicitly clear the previous failure before
        re-running (section 78) - including resetting each pipeline
        stage back to "waiting", so the Job Details view doesn't show
        stages left "done"/"failed" from the attempt that just failed."""
        with db_module.connect(self.db_path) as conn:
            row = conn.execute("SELECT stages_json FROM document_jobs WHERE id = ?", (job_id,)).fetchone()
            reset_stages = json.dumps([]) if row is None else json.dumps([
                {**stage, "status": "waiting"} for stage in json.loads(row["stages_json"])
            ])
            conn.execute(
                "UPDATE document_jobs SET status = 'queued', progress = 0, stage = NULL, "
                "stages_json = ?, error_code = NULL, error_message = NULL, started_at = NULL, "
                "completed_at = NULL, cancel_requested = 0 WHERE id = ?",
                (reset_stages, job_id),
            )

    def request_cancel(self, job_id: str) -> None:
        with db_module.connect(self.db_path) as conn:
            conn.execute("UPDATE document_jobs SET cancel_requested = 1 WHERE id = ?", (job_id,))

    def is_cancel_requested(self, job_id: str) -> bool:
        with db_module.connect(self.db_path) as conn:
            row = conn.execute("SELECT cancel_requested FROM document_jobs WHERE id = ?", (job_id,)).fetchone()
        return bool(row and row["cancel_requested"])

    def delete_job(self, job_id: str) -> None:
        with db_module.connect(self.db_path) as conn:
            conn.execute("DELETE FROM document_jobs WHERE id = ?", (job_id,))  # cascades to document_outputs

    def count_jobs_by_status(self, status: str) -> int:
        with db_module.connect(self.db_path) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM document_jobs WHERE status = ?", (status,)
            ).fetchone()[0]

    # -- outputs -------------------------------------------------------

    def create_output(self, output: DocumentOutput) -> None:
        with db_module.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO document_outputs
                   (id, job_id, output_type, storage_key, filename, file_size, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    output.id, output.job_id, output.output_type.value, output.storage_key,
                    output.filename, output.file_size, output.created_at,
                ),
            )

    def get_output(self, output_id: str) -> Optional[DocumentOutput]:
        with db_module.connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM document_outputs WHERE id = ?", (output_id,)).fetchone()
        return _row_to_output(row) if row else None

    def list_outputs(self, job_id: str) -> list[DocumentOutput]:
        with db_module.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM document_outputs WHERE job_id = ? ORDER BY created_at", (job_id,)
            ).fetchall()
        return [_row_to_output(r) for r in rows]

    # -- audit + dashboard ---------------------------------------------

    def audit(self, event: str, resource_id: Optional[str], detail: Optional[str] = None) -> None:
        with db_module.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO document_audit_log (event, resource_id, detail, created_at) VALUES (?, ?, ?, ?)",
                (event, resource_id, detail, now_iso()),
            )

    def overview_stats(self) -> dict:
        with db_module.connect(self.db_path) as conn:
            documents_total = conn.execute("SELECT COUNT(*) FROM documents WHERE status != 'deleted'").fetchone()[0]
            conversions = conn.execute(
                "SELECT COUNT(*) FROM document_jobs WHERE operation = 'pdf_to_markdown' AND status = 'completed'"
            ).fetchone()[0]
            merges = conn.execute(
                "SELECT COUNT(*) FROM document_jobs WHERE operation = 'merge' AND status = 'completed'"
            ).fetchone()[0]
            splits = conn.execute(
                "SELECT COUNT(*) FROM document_jobs WHERE operation = 'split' AND status = 'completed'"
            ).fetchone()[0]
            transcripts = conn.execute(
                "SELECT COUNT(*) FROM document_jobs WHERE operation = 'youtube_transcript' AND status = 'completed'"
            ).fetchone()[0]
            processing = conn.execute(
                "SELECT COUNT(*) FROM document_jobs WHERE status IN ('queued', 'uploading', 'processing')"
            ).fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM document_jobs WHERE status = 'failed'").fetchone()[0]
            documents_bytes = conn.execute(
                "SELECT COALESCE(SUM(file_size), 0) FROM documents WHERE status != 'deleted'"
            ).fetchone()[0]
            outputs_bytes = conn.execute("SELECT COALESCE(SUM(file_size), 0) FROM document_outputs").fetchone()[0]
            storage_bytes = documents_bytes + outputs_bytes
            avg_duration = conn.execute(
                "SELECT AVG((julianday(completed_at) - julianday(started_at)) * 86400.0) "
                "FROM document_jobs WHERE status = 'completed' AND started_at IS NOT NULL AND completed_at IS NOT NULL"
            ).fetchone()[0]
            recent = conn.execute(
                "SELECT * FROM documents WHERE status != 'deleted' ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
            recent_jobs = conn.execute(
                "SELECT * FROM document_jobs ORDER BY created_at DESC LIMIT 6"
            ).fetchall()
        return {
            "documents_total": documents_total,
            "conversions": conversions,
            "merges": merges,
            "splits": splits,
            "transcripts": transcripts,
            "processing": processing,
            "failed": failed,
            "storage_bytes": storage_bytes,
            "avg_duration_seconds": round(avg_duration, 1) if avg_duration else None,
            "recent_documents": [_row_to_document(r) for r in recent],
            "recent_jobs": [_row_to_job(r) for r in recent_jobs],
        }
