"""SQLite persistence for documents, jobs and outputs.

Why SQLite rather than an ORM/Postgres: this module extends a local,
single-user tool (see src/webapp.py's own note: no accounts, binds to
127.0.0.1 only). The existing job tracker was a plain in-memory dict
that lost all history on restart; that's the one thing worth fixing
here so History/Files/Jobs survive a restart, not a reason to adopt a
client-server database or an ORM this project doesn't otherwise use.
A dependency-free stdlib connection per call, with WAL mode for
readers/writers concurrency, is enough at this scale.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    page_count INTEGER,
    checksum_sha256 TEXT,
    status TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'upload',
    source_job_id TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS document_jobs (
    id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0,
    stage TEXT,
    stages_json TEXT NOT NULL DEFAULT '[]',
    logs_json TEXT NOT NULL DEFAULT '[]',
    input_document_ids_json TEXT NOT NULL DEFAULT '[]',
    options_json TEXT NOT NULL DEFAULT '{}',
    error_code TEXT,
    error_message TEXT,
    result_summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS document_outputs (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES document_jobs(id) ON DELETE CASCADE,
    output_type TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event TEXT NOT NULL,
    resource_id TEXT,
    detail TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON document_jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON document_jobs(status);
CREATE INDEX IF NOT EXISTS idx_outputs_job_id ON document_outputs(job_id);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
"""


# Columns added after the initial release: applied with ALTER TABLE
# against a database that may already exist on disk, since SQLite has
# no "ADD COLUMN IF NOT EXISTS" - each is a no-op (caught and ignored)
# once already applied.
_MIGRATIONS = [
    "ALTER TABLE documents ADD COLUMN source TEXT NOT NULL DEFAULT 'upload'",
    "ALTER TABLE documents ADD COLUMN source_job_id TEXT",
    "ALTER TABLE document_jobs ADD COLUMN logs_json TEXT NOT NULL DEFAULT '[]'",
]


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_SCHEMA)
        for statement in _MIGRATIONS:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError:
                pass  # Column already exists - already migrated.
        conn.commit()
    finally:
        conn.close()


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
