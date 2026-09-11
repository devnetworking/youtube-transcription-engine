"""Pre-success output validation (spec section 23).

Runs after files are written and before the CLI reports success for a
video, so a broken write (empty file, bad encoding, missing fields)
surfaces as an error rather than a silently wrong "success".
"""

from __future__ import annotations

from pathlib import Path

from ..models import TranscriptSegment, VideoMetadata
from .timestamps import is_ordered


def validate_output(
    md_path: Path,
    txt_path: Path,
    metadata: VideoMetadata,
    segments: list[TranscriptSegment],
) -> list[str]:
    issues: list[str] = []

    if not md_path.exists():
        issues.append("transcript.md was not created.")
    if not txt_path.exists():
        issues.append("transcript.txt was not created.")
    if issues:
        return issues  # Can't check contents of files that don't exist.

    md_bytes = md_path.read_bytes()
    txt_bytes = txt_path.read_bytes()

    if not md_bytes:
        issues.append("transcript.md is empty.")
    if not txt_bytes:
        issues.append("transcript.txt is empty.")

    try:
        md_text = md_bytes.decode("utf-8")
    except UnicodeDecodeError:
        issues.append("transcript.md is not valid UTF-8.")
        md_text = ""

    try:
        txt_text = txt_bytes.decode("utf-8")
    except UnicodeDecodeError:
        issues.append("transcript.txt is not valid UTF-8.")
        txt_text = ""

    if not metadata.title:
        issues.append("Video title is missing from metadata.")
    if not metadata.url:
        issues.append("Video URL is missing from metadata.")

    if not any(s.text.strip() for s in segments):
        issues.append("Transcript contains no meaningful text.")

    starts = [s.start for s in segments]
    if not is_ordered(starts):
        issues.append("Transcript timestamps are not in order.")

    texts = [s.text.strip().lower() for s in segments if s.text.strip()]
    duplicate_run = any(a == b for a, b in zip(texts, texts[1:]))
    if duplicate_run:
        issues.append("Duplicate consecutive caption blocks remain in the transcript.")

    if md_text and not (md_text.lstrip().startswith("#") and "## Video Information" in md_text):
        issues.append("transcript.md does not have the expected Markdown structure.")

    if txt_text and ("|---" in txt_text or "| --- " in txt_text):
        issues.append("transcript.txt unexpectedly contains Markdown table formatting.")

    return issues
