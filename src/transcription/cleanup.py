"""Intelligent, non-destructive transcript cleaning (spec section 7).

This only removes artifacts of the caption/STT pipeline itself
(duplicated cue fragments, caption-boundary overlap, stray whitespace,
malformed punctuation spacing). It never rewrites words a speaker
actually said - genuine disfluencies and mid-sentence repeats are left
alone, per the fidelity rules in section 6.
"""

from __future__ import annotations

import re

from ..models import TranscriptSegment

_FILLER_WORDS = {
    "um", "uh", "uhh", "umm", "erm", "hmm",
}

_WHITESPACE_RE = re.compile(r"[ \t]+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.!?;:])")
_MULTI_PUNCT_RE = re.compile(r"([,.!?;:])\1+")


def clean_segments(segments: list[TranscriptSegment], remove_filler_words: bool = False) -> list[TranscriptSegment]:
    deduped = _remove_duplicate_segments(segments)
    trimmed = _trim_boundary_overlap(deduped)

    cleaned: list[TranscriptSegment] = []
    for seg in trimmed:
        text = _normalize_text(seg.text)
        if remove_filler_words:
            text = _strip_filler_words(text)
        if not text:
            continue
        cleaned.append(seg.model_copy(update={"text": text}))

    return cleaned


def _remove_duplicate_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    """Drop segments that are exact repeats of the immediately preceding one.

    Auto-captions occasionally emit the same cue twice at nearly
    identical timestamps; this is a pipeline artifact, not speech.
    """
    result: list[TranscriptSegment] = []
    for seg in segments:
        if result and _normalize_text(result[-1].text).lower() == _normalize_text(seg.text).lower():
            continue
        result.append(seg)
    return result


def _trim_boundary_overlap(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    """Trim rolling-caption overlap where one cue repeats the tail of the previous cue.

    Example artifact: cue A = "...and then we deploy the", cue B = "the
    model to production" -> B is trimmed to "model to production".
    """
    result: list[TranscriptSegment] = []
    for seg in segments:
        if result:
            prev_words = _normalize_text(result[-1].text).split()
            cur_words = _normalize_text(seg.text).split()
            overlap = _longest_common_overlap(prev_words, cur_words)
            if overlap:
                seg = seg.model_copy(update={"text": " ".join(cur_words[overlap:])})
        if seg.text.strip():
            result.append(seg)
    return result


def _longest_common_overlap(prev_words: list[str], cur_words: list[str], max_check: int = 8) -> int:
    limit = min(len(prev_words), len(cur_words), max_check)
    for size in range(limit, 0, -1):
        if [w.lower() for w in prev_words[-size:]] == [w.lower() for w in cur_words[:size]]:
            return size
    return 0


def _normalize_text(text: str) -> str:
    text = text.replace("\n", " ")
    text = _WHITESPACE_RE.sub(" ", text)
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = _MULTI_PUNCT_RE.sub(r"\1", text)
    return text.strip()


def _strip_filler_words(text: str) -> str:
    words = text.split()
    kept = [w for w in words if w.strip(",.!?;:").lower() not in _FILLER_WORDS]
    return " ".join(kept)
