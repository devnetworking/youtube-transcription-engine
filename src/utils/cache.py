"""Resume/cache support (spec section 22).

Intermediate artifacts (extracted audio, raw transcription) are keyed by
video_id + transcription_source + language + model so an interrupted or
re-run job can skip re-downloading audio and re-transcribing when
nothing relevant has changed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional


def cache_key(video_id: str, source: str, language: str | None, model: str | None) -> str:
    raw = f"{video_id}|{source}|{language or ''}|{model or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class CacheStore:
    """A tiny filesystem-backed cache, one JSON file (+ optional blobs) per key."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _paths(self, key: str) -> tuple[Path, Path]:
        return self.cache_dir / f"{key}.json", self.cache_dir / key

    def get(self, key: str) -> Optional[dict[str, Any]]:
        meta_path, _ = self._paths(key)
        if not meta_path.exists():
            return None
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def set(self, key: str, data: dict[str, Any]) -> None:
        meta_path, _ = self._paths(key)
        meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def blob_dir(self, key: str) -> Path:
        _, blob_dir = self._paths(key)
        blob_dir.mkdir(parents=True, exist_ok=True)
        return blob_dir
