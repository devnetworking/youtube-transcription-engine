"""Orchestrates the job queue against the repository (sections 21, 77-79).

Routes call here to submit/cancel/retry; this is the only place that
knows how to turn a stored DocumentJob back into a runnable target by
delegating to whichever operation service created it in the first
place.
"""

from __future__ import annotations

from typing import Optional

from ..exceptions import DocumentError, JobNotFoundError
from ..job_queue import JobQueue
from ..models import DocumentJob, JobStatus
from ..repository import DocumentRepository
from ..storage import OUTPUTS, StorageProvider


class JobService:
    def __init__(
        self, repository: DocumentRepository, job_queue: JobQueue, operation_services: dict, storage: StorageProvider
    ):
        self.repository = repository
        self.job_queue = job_queue
        # {JobOperation: service instance exposing build_target(job)}
        self._operation_services = operation_services
        self.storage = storage

    def get(self, job_id: str) -> DocumentJob:
        job = self.repository.get_job(job_id)
        if job is None:
            raise JobNotFoundError(f"Job '{job_id}' was not found.")
        return job

    def list(
        self, status: Optional[str] = None, operation: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> list[DocumentJob]:
        return self.repository.list_jobs(status=status, operation=operation, limit=limit, offset=offset)

    def outputs(self, job_id: str):
        self.get(job_id)
        return self.repository.list_outputs(job_id)

    def submit(self, job: DocumentJob) -> None:
        service = self._operation_services[job.operation]
        self.job_queue.submit(job.id, service.build_target(job))

    def retry(self, job_id: str) -> DocumentJob:
        job = self.get(job_id)
        if job.status != JobStatus.FAILED:
            raise DocumentError("Only a failed job can be retried.")
        # Reset stages/status in the DB *before* building the target, so
        # the closure captures a fresh "waiting" stage list instead of
        # the one left "done"/"failed" by the attempt that just failed.
        self.repository.reset_job_for_retry(job_id)
        fresh_job = self.get(job_id)
        service = self._operation_services[job.operation]
        self.job_queue.submit(job_id, service.build_target(fresh_job))
        return fresh_job

    def cancel(self, job_id: str) -> DocumentJob:
        job = self.get(job_id)
        if job.status not in (JobStatus.QUEUED, JobStatus.PROCESSING):
            raise DocumentError(f"Job is already {job.status.value} and cannot be cancelled.")
        self.job_queue.cancel(job_id)
        return self.get(job_id)

    def delete(self, job_id: str) -> None:
        job = self.get(job_id)
        if job.status in (JobStatus.QUEUED, JobStatus.PROCESSING):
            raise DocumentError("Cancel this job before deleting it.")
        self.storage.delete_entity(OUTPUTS, job_id)
        self.repository.delete_job(job_id)
