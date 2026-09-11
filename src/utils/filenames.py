"""Filesystem-safe naming helpers (spec section 15)."""

from __future__ import annotations

import re
from pathlib import Path

_INVALID_CHARS = r'[\/\\:*?"<>|]'
_MAX_NAME_LENGTH = 100


def sanitize_filename(title: str | None, fallback: str = "untitled_video") -> str:
    """Turn an arbitrary video title into a safe directory/file name.

    Treats the title as untrusted input: strips path separators and
    reserved characters so it can never be used for path traversal or
    to escape the output directory (spec section 27).
    """
    name = (title or "").strip()
    if not name:
        name = fallback

    name = re.sub(_INVALID_CHARS, "_", name)
    # Collapse whitespace/underscern runs and swap spaces for underscores.
    name = re.sub(r"\s+", "_", name.strip())
    name = re.sub(r"_+", "_", name)
    # Strip leading/trailing dots and underscores (Windows reserved trailing dot).
    name = name.strip("._")

    if not name:
        name = fallback

    if len(name) > _MAX_NAME_LENGTH:
        name = name[:_MAX_NAME_LENGTH].rstrip("._")

    # Guard against Windows reserved device names.
    reserved = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    if name.upper() in reserved:
        name = f"_{name}"

    return name


def unique_output_dir(output_root: Path, title: str | None, video_id: str | None) -> Path:
    """Resolve the output directory for a video, disambiguating title clashes.

    If a directory with the same sanitized title already exists and was
    produced for a *different* video (checked via its metadata.json),
    the video ID is appended so the two videos never collide.
    """
    base_name = sanitize_filename(title, fallback=video_id or "untitled_video")
    candidate = output_root / base_name

    if not candidate.exists():
        return candidate

    existing_meta = candidate / "metadata.json"
    if existing_meta.exists():
        try:
            import json

            data = json.loads(existing_meta.read_text(encoding="utf-8"))
            if video_id and data.get("video_id") == video_id:
                return candidate  # Same video: reuse the directory (resume/cache).
        except (OSError, ValueError):
            pass

    if video_id:
        suffixed = output_root / f"{base_name}_{video_id}"
        return suffixed

    # No video_id to disambiguate with: fall back to a numeric suffix.
    counter = 2
    while (output_root / f"{base_name}_{counter}").exists():
        counter += 1
    return output_root / f"{base_name}_{counter}"
