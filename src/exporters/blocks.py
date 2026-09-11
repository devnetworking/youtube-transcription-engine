"""Shared timestamp-block windowing used by both the Markdown and TXT
exporters (spec sections 9, 11, 12), so the two outputs stay consistent
and the windowing logic exists in exactly one place.
"""

from __future__ import annotations

from ..analysis.technical import is_code_like
from ..models import Chapter, TranscriptSegment

_TARGET_BLOCK_SECONDS = 45  # Midpoint of the spec's 30-60s guidance.


class TranscriptBlock:
    __slots__ = ("start_seconds", "text", "is_code")

    def __init__(self, start_seconds: float, text: str, is_code: bool = False):
        self.start_seconds = start_seconds
        self.text = text
        self.is_code = is_code


class ChapterSection:
    __slots__ = ("chapter", "blocks")

    def __init__(self, chapter: Chapter, blocks: list[TranscriptBlock]):
        self.chapter = chapter
        self.blocks = blocks


def group_by_chapter(segments: list[TranscriptSegment], chapters: list[Chapter]) -> list[ChapterSection]:
    if not chapters:
        chapters = [Chapter(index=1, title="Full Transcript", timestamp_seconds=0.0, source="inferred")]

    ordered = sorted(chapters, key=lambda c: c.timestamp_seconds)
    sections: list[ChapterSection] = []
    for i, chapter in enumerate(ordered):
        start = chapter.timestamp_seconds
        end = ordered[i + 1].timestamp_seconds if i + 1 < len(ordered) else float("inf")
        chapter_segments = [s for s in segments if start <= s.start < end]
        sections.append(ChapterSection(chapter=chapter, blocks=build_blocks(chapter_segments)))
    return sections


def build_blocks(segments: list[TranscriptSegment], target_seconds: float = _TARGET_BLOCK_SECONDS) -> list[TranscriptBlock]:
    if not segments:
        return []

    blocks: list[TranscriptBlock] = []
    block_start = segments[0].start
    buffer: list[str] = []

    def flush(next_start: float) -> None:
        nonlocal buffer, block_start
        if buffer:
            blocks.append(TranscriptBlock(block_start, " ".join(buffer)))
            buffer = []
        block_start = next_start

    for seg in segments:
        text = seg.text
        if seg.uncertain:
            marker = f"[uncertain: {seg.uncertain_reason}]" if seg.uncertain_reason else "[uncertain]"
            text = f"{text} {marker}"

        if is_code_like(seg.text):
            flush(seg.start)
            blocks.append(TranscriptBlock(seg.start, text, is_code=True))
            block_start = seg.end if seg.end is not None else seg.start
            continue

        if buffer and (seg.start - block_start) >= target_seconds:
            flush(seg.start)
        buffer.append(text)

    if buffer:
        blocks.append(TranscriptBlock(block_start, " ".join(buffer)))

    return blocks


def flatten_blocks(sections: list[ChapterSection]) -> list[TranscriptBlock]:
    flat: list[TranscriptBlock] = []
    for section in sections:
        flat.extend(section.blocks)
    return flat
