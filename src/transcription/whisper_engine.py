"""Local speech-to-text fallback via faster-whisper (spec section 4, Priority 3).

faster-whisper (and its heavy native dependencies) is an optional
dependency: importing it happens lazily, inside the function that needs
it, so the rest of the tool works fine without it installed until this
fallback path is actually reached.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..exceptions import InsufficientMemoryError, WhisperModelError, WhisperUnavailableError
from ..models import TranscriptionResult, TranscriptionSource, TranscriptSegment

# Approximate minimum available RAM (GiB) recommended for each model size.
_MODEL_MEMORY_REQUIREMENTS_GB = [
    ("large-v3", 10),
    ("medium", 5),
    ("small", 2),
    ("base", 1),
    ("tiny", 0),
]

# Segments with an average log-probability below this are flagged uncertain.
_LOW_CONFIDENCE_LOGPROB = -1.0
_HIGH_NO_SPEECH_PROB = 0.6


def select_model_size(requested: Optional[str] = None) -> str:
    """Pick a whisper model size, honoring an explicit request or sizing
    it to the machine's available memory (spec section 4, item 4)."""
    if requested and requested != "auto":
        return requested

    try:
        import psutil

        available_gb = psutil.virtual_memory().available / (1024**3)
    except ImportError:
        return "small"  # Reasonable balanced default without psutil.

    for model_size, min_gb in _MODEL_MEMORY_REQUIREMENTS_GB:
        if available_gb >= min_gb:
            return model_size
    return "tiny"


def transcribe_audio(
    audio_path: Path,
    model_size: Optional[str] = None,
    language: Optional[str] = None,
) -> TranscriptionResult:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise WhisperUnavailableError(
            "faster-whisper is not installed. Install it (see requirements.txt) "
            "to enable local audio transcription."
        ) from exc

    resolved_size = select_model_size(model_size)

    try:
        model = WhisperModel(resolved_size, device="auto", compute_type="auto")
    except Exception as exc:  # noqa: BLE001
        message = str(exc).lower()
        if "memory" in message or "alloc" in message:
            raise InsufficientMemoryError(
                f"Not enough memory to load Whisper model '{resolved_size}': {exc}"
            ) from exc
        raise WhisperModelError(f"Failed to load Whisper model '{resolved_size}': {exc}") from exc

    try:
        segments_iter, info = model.transcribe(
            str(audio_path),
            language=None if not language or language == "auto" else language,
            word_timestamps=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise WhisperModelError(f"Whisper transcription failed: {exc}") from exc

    segments: list[TranscriptSegment] = []
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if not text:
            continue
        uncertain = False
        reason = None
        if getattr(seg, "avg_logprob", 0.0) is not None and seg.avg_logprob < _LOW_CONFIDENCE_LOGPROB:
            uncertain = True
            reason = "low_confidence"
        if getattr(seg, "no_speech_prob", 0.0) is not None and seg.no_speech_prob > _HIGH_NO_SPEECH_PROB:
            uncertain = True
            reason = "possible_non_speech"
        segments.append(
            TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=text,
                uncertain=uncertain,
                uncertain_reason=reason,
            )
        )

    if not segments:
        raise WhisperModelError("Whisper produced no transcribable speech segments.")

    detected_language = getattr(info, "language", None)
    low_confidence = getattr(info, "language_probability", 1.0) is not None and info.language_probability < 0.6

    return TranscriptionResult(
        segments=segments,
        source=TranscriptionSource.WHISPER,
        language=detected_language,
        model=resolved_size,
        low_confidence_language=bool(low_confidence),
    )
