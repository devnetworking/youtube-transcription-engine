"""Retention cleanup (section 58).

Runs once when the server starts rather than on a background scheduler:
this is the same "no hot background thread beyond what the job queue
already needs" posture as the rest of the module, and a local tool that
gets restarted periodically (README: the server doesn't hot-reload, so
restarts are already routine) doesn't need a persistent timer or a new
dependency (APScheduler) just to keep `outputs/` from growing forever.
"""

from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime

from .config import DocumentSettings
from .repository import DocumentRepository
from .storage import OUTPUTS, TMP, StorageProvider

logger = logging.getLogger("documents")

_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def run_retention_cleanup(repository: DocumentRepository, storage: StorageProvider, settings: DocumentSettings) -> None:
    """Best-effort: a bug here must never prevent the server from
    starting, so every step is isolated and logged, not raised."""
    try:
        _cleanup_old_job_outputs(repository, storage, settings.output_retention_days)
    except Exception:
        logger.exception("Job output retention cleanup failed")
    try:
        _cleanup_stale_tmp_dirs(storage, settings.temp_file_retention_hours)
    except Exception:
        logger.exception("Temporary file retention cleanup failed")


def _age_seconds(iso_timestamp: str) -> float:
    return time.time() - datetime.fromisoformat(iso_timestamp).timestamp()


def _cleanup_old_job_outputs(repository: DocumentRepository, storage: StorageProvider, retention_days: int) -> None:
    if retention_days <= 0:
        return
    max_age = retention_days * 86400
    removed = 0
    for job in repository.list_jobs(limit=100_000):
        if job.status.value not in _TERMINAL_STATUSES:
            continue
        reference = job.completed_at or job.created_at
        if not reference:
            continue
        try:
            if _age_seconds(reference) <= max_age:
                continue
        except ValueError:
            continue
        storage.delete_entity(OUTPUTS, job.id)
        repository.delete_job(job.id)
        removed += 1
    if removed:
        logger.info("Retention cleanup removed %d job(s) older than %d day(s)", removed, retention_days)


def _cleanup_stale_tmp_dirs(storage: StorageProvider, retention_hours: int) -> None:
    if retention_hours <= 0:
        return
    tmp_root = storage.abs_path(TMP)
    if not tmp_root.exists():
        return
    max_age = retention_hours * 3600
    removed = 0
    for entry in tmp_root.iterdir():
        if not entry.is_dir():
            continue
        if time.time() - entry.stat().st_mtime > max_age:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    if removed:
        logger.info("Retention cleanup removed %d stale temporary director(y/ies)", removed)
