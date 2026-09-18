"""Configuration for the document processing module.

Same precedence rule as src/config.py (lowest to highest): built-in
defaults -> YAML config file -> environment variables, here prefixed
`DOCS_` instead of `YTT_` since this is a separate settings surface.
Kept as its own file rather than folding into AppConfig: these are
service-level limits (upload size, retention, worker count), not
per-request transcription options.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel


class DocumentSettings(BaseModel):
    # Storage
    data_dir: str = "documents_data"

    # Upload / resource limits (section 5, 31, 34) - configurable, never
    # hard-coded arbitrarily in the handlers themselves.
    max_upload_size_mb: int = 512
    max_pages_per_document: int = 20000
    max_files_per_merge: int = 50
    max_concurrent_jobs: int = 2
    job_timeout_seconds: int = 1800

    # Retention (section 58)
    temp_file_retention_hours: int = 24
    output_retention_days: int = 30

    # PDF -> Markdown defaults (section 12, 56)
    default_ocr_mode: str = "auto"  # "auto" | "always" | "never"
    default_extract_images: bool = True
    default_detect_tables: bool = True
    ocr_language: str = "auto"

    # Security (section 31, 56)
    allowed_upload_extensions: list[str] = ["pdf"]


_ENV_PREFIX = "DOCS_"


def load_document_settings(config_path: Optional[Path] = None) -> DocumentSettings:
    data: dict = {}

    if config_path is not None and config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict) and isinstance(loaded.get("documents"), dict):
            data.update(loaded["documents"])

    for field_name in DocumentSettings.model_fields:
        env_name = f"{_ENV_PREFIX}{field_name.upper()}"
        if env_name in os.environ:
            raw = os.environ[env_name]
            if field_name == "allowed_upload_extensions":
                data[field_name] = [ext.strip().lower() for ext in raw.split(",") if ext.strip()]
            else:
                data[field_name] = raw

    return DocumentSettings(**data)
