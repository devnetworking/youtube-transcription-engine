"""Chapter detection (spec section 10): prefer YouTube's own chapters,
otherwise infer chapters from topic drift in the transcript.
"""

from __future__ import annotations

from typing import Any

from ..models import Chapter, TranscriptSegment
from .keywords import extract_keywords

_MIN_CHAPTER_SECONDS = 90  # Avoid excessive fragmentation.
_TARGET_CHAPTER_SECONDS = 300  # ~5 minutes as a default window size.


def chapters_from_youtube(raw_chapters: list[dict[str, Any]] | None) -> list[Chapter]:
    if not raw_chapters:
        return []
    chapters = []
    for i, ch in enumerate(raw_chapters, start=1):
        title = (ch.get("title") or f"Chapter {i}").strip()
        start = ch.get("start_time")
        if start is None:
            continue
        chapters.append(Chapter(index=i, title=title, timestamp_seconds=float(start), source="youtube"))
    return chapters


def infer_chapters(segments: list[TranscriptSegment], language: str | None = None) -> list[Chapter]:
    """Infer semantic chapters by splitting into topic windows and titling
    each window with its most distinctive keywords.

    This is an intentionally simple, deterministic heuristic (equal-ish
    time windows sized to the video length, titled from local word
    frequency) rather than genuine topic-transition detection, since the
    project has no LLM/embedding dependency available at runtime.
    """
    if not segments:
        return []

    total_duration = segments[-1].end or segments[-1].start
    if total_duration <= 0:
        return []

    if total_duration <= _MIN_CHAPTER_SECONDS * 1.5:
        return [Chapter(index=1, title="Full Content", timestamp_seconds=0.0, source="inferred")]

    window_count = max(1, round(total_duration / _TARGET_CHAPTER_SECONDS))
    window_size = total_duration / window_count

    chapters: list[Chapter] = []
    for i in range(window_count):
        window_start = i * window_size
        window_end = window_start + window_size
        window_text = " ".join(
            seg.text for seg in segments if window_start <= seg.start < window_end
        )
        title = _title_from_keywords(window_text, index=i + 1, language=language)
        chapters.append(Chapter(index=i + 1, title=title, timestamp_seconds=window_start, source="inferred"))

    return _merge_short_chapters(chapters, total_duration)


def _title_from_keywords(window_text: str, index: int, language: str | None = None) -> str:
    keywords = extract_keywords(window_text, top_n=3, language=language)
    if not keywords:
        return f"Part {index}"
    return " / ".join(word.capitalize() for word in keywords)


def _merge_short_chapters(chapters: list[Chapter], total_duration: float) -> list[Chapter]:
    if len(chapters) <= 1:
        return chapters

    merged = [chapters[0]]
    for ch in chapters[1:]:
        prev = merged[-1]
        if ch.timestamp_seconds - prev.timestamp_seconds < _MIN_CHAPTER_SECONDS:
            continue  # Too close to the previous chapter: drop the boundary.
        merged.append(ch)

    for i, ch in enumerate(merged, start=1):
        ch.index = i

    return merged
