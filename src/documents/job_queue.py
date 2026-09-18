"""Background job execution (sections 21, 28, 34, 77-79).

A bounded `ThreadPoolExecutor` rather than Celery/Redis: this is a
local, single-machine tool (the existing webapp.py already runs each
YouTube transcription in a plain `threading.Thread`), and a real
message broker would be infrastructure with nothing here to justify
it. `max_workers` bounds how many jobs actually run at once; anything
submitted beyond that sits in the executor's own queue, which is what
gives us the "Queued" status for free.

Cancellation is cooperative (`CancelToken.check()`), not a hard thread
kill: a Python thread cannot safely be killed mid-call into a native
extension (PyMuPDF, Tesseract) without risking a corrupted process, so
every pipeline stage boundary checks the token instead. The same token
also enforces the configured job timeout, since Python threads can't be
preempted from the outside either.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from .exceptions import JobCancelledError
from .models import JobStatus, PipelineStage
from .repository import DocumentRepository, now_iso


class CancelToken:
    def __init__(self, repository: DocumentRepository, job_id: str, timeout_seconds: Optional[int] = None):
        self._repository = repository
        self.job_id = job_id
        self._deadline = time.monotonic() + timeout_seconds if timeout_seconds else None

    def check(self) -> None:
        if self._repository.is_cancel_requested(self.job_id):
            raise JobCancelledError("Job was cancelled by the user.")
        if self._deadline is not None and time.monotonic() > self._deadline:
            raise JobCancelledError("Job exceeded the configured processing timeout.")

    def set_stage(self, stages: list[PipelineStage], key: str, progress: float) -> None:
        for stage in stages:
            if stage.key == key:
                stage.status = "running"
            elif stage.status == "running":
                stage.status = "done"
        self._repository.update_job(self.job_id, stage=key, stages=stages, progress=progress)

    def finish_stages(self, stages: list[PipelineStage]) -> None:
        for stage in stages:
            if stage.status == "running":
                stage.status = "done"
        self._repository.update_job(self.job_id, stages=stages, progress=1.0)


JobTarget = Callable[[CancelToken], None]


class JobQueue:
    def __init__(self, repository: DocumentRepository, max_workers: int = 2, job_timeout_seconds: int = 1800):
        self._repository = repository
        self._executor = ThreadPoolExecutor(max_workers=max(1, max_workers), thread_name_prefix="doc-job")
        self._job_timeout_seconds = job_timeout_seconds
        self._lock = threading.Lock()
        self._futures: dict[str, object] = {}

    def submit(self, job_id: str, target: JobTarget) -> None:
        token = CancelToken(self._repository, job_id, self._job_timeout_seconds)
        future = self._executor.submit(self._run, job_id, target, token)
        with self._lock:
            self._futures[job_id] = future

    def _run(self, job_id: str, target: JobTarget, token: CancelToken) -> None:
        self._repository.update_job(job_id, status=JobStatus.PROCESSING, started_at=now_iso())
        try:
            target(token)
            self._repository.update_job(job_id, status=JobStatus.COMPLETED, completed_at=now_iso(), progress=1.0)
            self._repository.audit("PDF_JOB_COMPLETED", job_id)
        except JobCancelledError as exc:
            status = JobStatus.CANCELLED if "cancel" in str(exc).lower() else JobStatus.FAILED
            self._repository.update_job(
                job_id,
                status=status,
                completed_at=now_iso(),
                error_code="cancelled" if status == JobStatus.CANCELLED else "timeout",
                error_message=str(exc),
            )
            self._repository.audit("PDF_JOB_CANCELLED", job_id, str(exc))
        except Exception as exc:  # noqa: BLE001 - a bug here must not leave the job stuck "processing"
            self._repository.update_job(
                job_id,
                status=JobStatus.FAILED,
                completed_at=now_iso(),
                error_code="processing_error",
                error_message=str(exc),
            )
            self._repository.audit("PDF_JOB_FAILED", job_id, str(exc))
        finally:
            with self._lock:
                self._futures.pop(job_id, None)

    def cancel(self, job_id: str) -> None:
        self._repository.request_cancel(job_id)
