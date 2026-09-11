"""Fallback orchestration across caption/STT sources (spec section 4)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from ..exceptions import (
    CaptionsUnavailableError,
    NoTranscriptionSourceError,
    WhisperUnavailableError,
)
from ..models import TranscriptionResult, TranscriptionSource, TranscriptSegment
from ..utils.cache import CacheStore, cache_key
from ..youtube import audio as audio_module
from ..youtube import captions as captions_module
from . import whisper_engine


def obtain_transcript(
    *,
    video_id: str,
    url: str,
    language: Optional[str],
    whisper_model: Optional[str],
    force_whisper: bool,
    work_dir: Path,
    warnings: list[str],
    notify: Optional[Callable[[str], None]] = None,
    verbose: bool = False,
    cache_dir: Optional[Path] = None,
) -> TranscriptionResult:
    """Run the layered fallback strategy and return the first usable transcript.

    When `cache_dir` is given, a successful Whisper transcription is
    cached (keyed by video_id + language + model) and reused on a later
    call with the same key instead of re-downloading audio and
    re-transcribing (spec section 22). Captions aren't cached: fetching
    them is already a single cheap request, so there's nothing
    expensive to save there.
    """
    notify = notify or (lambda _msg: None)

    if not force_whisper:
        try:
            return captions_module.get_captions(video_id, preferred_language=language)
        except CaptionsUnavailableError as exc:
            warnings.append(f"Captions unavailable, falling back to audio transcription: {exc}")

    cache = CacheStore(cache_dir) if cache_dir else None
    key = cache_key(video_id, "whisper", language, whisper_model) if cache else None

    if cache and key:
        cached = cache.get(key)
        if cached:
            notify("Reusing cached Whisper transcript (skipping re-download and re-transcription)...")
            return TranscriptionResult(
                segments=[TranscriptSegment(**s) for s in cached["segments"]],
                source=TranscriptionSource.WHISPER,
                language=cached.get("language"),
                model=cached.get("model"),
                low_confidence_language=cached.get("low_confidence_language", False),
            )

    notify("Extracting audio...")
    audio_path = audio_module.download_audio(url, video_id, work_dir, verbose=verbose, report=notify)
    notify(f"Transcribing with Whisper (model={whisper_model or 'auto'})...")
    try:
        result = whisper_engine.transcribe_audio(audio_path, model_size=whisper_model, language=language)
    except WhisperUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise NoTranscriptionSourceError(
            f"Both captions and audio transcription failed for {video_id}: {exc}"
        ) from exc

    if cache and key:
        cache.set(
            key,
            {
                "segments": [s.model_dump(mode="json") for s in result.segments],
                "language": result.language,
                "model": result.model,
                "low_confidence_language": result.low_confidence_language,
            },
        )

    return result
