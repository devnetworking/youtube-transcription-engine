"""Configuration loading (spec section 19).

Precedence, lowest to highest: built-in defaults -> YAML config file ->
environment variables (YTT_* prefix) -> explicit CLI options.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel


class AppConfig(BaseModel):
    output_dir: str = "output"
    language: str = "auto"
    prefer_captions: bool = True
    whisper_model: str = "auto"
    timestamps: bool = True
    chapter_detection: bool = True
    generate_summary: bool = True
    generate_txt: bool = True
    generate_markdown: bool = True
    generate_metadata: bool = True
    diarize: bool = False
    force_whisper: bool = False
    research_mode: bool = False
    remove_filler_words: bool = False
    verbose: bool = False


_ENV_PREFIX = "YTT_"


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    data: dict = {}

    if config_path is not None and config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            data.update(loaded)

    for field_name in AppConfig.model_fields:
        env_name = f"{_ENV_PREFIX}{field_name.upper()}"
        if env_name in os.environ:
            data[field_name] = os.environ[env_name]

    return AppConfig(**data)
