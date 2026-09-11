"""Transcription quality scoring (spec section 24).

The score is derived only from observable pipeline signals (source,
share of uncertain segments, language-detection confidence) - never a
claim about accuracy we have no evidence for.
"""

from __future__ import annotations

from ..models import QualityLevel, TranscriptionResult, TranscriptionSource


def compute_quality(result: TranscriptionResult) -> QualityLevel:
    total = len(result.segments)
    uncertain = sum(1 for s in result.segments if s.uncertain)
    uncertain_ratio = (uncertain / total) if total else 0.0

    if result.source == TranscriptionSource.MANUAL_CAPTIONS:
        return QualityLevel.HIGH if uncertain_ratio < 0.05 else QualityLevel.MEDIUM

    if result.source == TranscriptionSource.AUTO_CAPTIONS:
        if uncertain_ratio > 0.15:
            return QualityLevel.LOW
        return QualityLevel.MEDIUM

    # Whisper: weigh model size and per-segment confidence flags together.
    if result.low_confidence_language:
        return QualityLevel.LOW

    large_models = {"medium", "large-v3", "large-v2", "large"}
    if uncertain_ratio > 0.2:
        return QualityLevel.LOW
    if result.model in large_models and uncertain_ratio < 0.08:
        return QualityLevel.HIGH
    return QualityLevel.MEDIUM
