from pathlib import Path

import pytest

from src.exceptions import CaptionsUnavailableError, NoTranscriptionSourceError, WhisperUnavailableError
from src.models import TranscriptionResult, TranscriptionSource, TranscriptSegment
from src.transcription import engine


def test_falls_back_to_whisper_when_captions_missing(monkeypatch, tmp_path):
    def fake_get_captions(video_id, preferred_language=None):
        raise CaptionsUnavailableError("no captions")

    def fake_download_audio(url, video_id, work_dir, **kwargs):
        return Path(work_dir) / f"{video_id}.wav"

    whisper_result = TranscriptionResult(
        segments=[TranscriptSegment(start=0, end=1, text="hi")],
        source=TranscriptionSource.WHISPER,
        language="en",
        model="small",
    )

    monkeypatch.setattr(engine.captions_module, "get_captions", fake_get_captions)
    monkeypatch.setattr(engine.audio_module, "download_audio", fake_download_audio)
    monkeypatch.setattr(engine.whisper_engine, "transcribe_audio", lambda *a, **k: whisper_result)

    warnings: list[str] = []
    result = engine.obtain_transcript(
        video_id="abc123",
        url="https://www.youtube.com/watch?v=abc123",
        language=None,
        whisper_model="small",
        force_whisper=False,
        work_dir=tmp_path,
        warnings=warnings,
    )

    assert result.source == TranscriptionSource.WHISPER
    assert warnings  # a warning was recorded explaining the fallback


def test_raises_no_transcription_source_when_everything_fails(monkeypatch, tmp_path):
    def fake_get_captions(video_id, preferred_language=None):
        raise CaptionsUnavailableError("no captions")

    def fake_download_audio(url, video_id, work_dir, **kwargs):
        return Path(work_dir) / f"{video_id}.wav"

    def fake_transcribe(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(engine.captions_module, "get_captions", fake_get_captions)
    monkeypatch.setattr(engine.audio_module, "download_audio", fake_download_audio)
    monkeypatch.setattr(engine.whisper_engine, "transcribe_audio", fake_transcribe)

    with pytest.raises(NoTranscriptionSourceError):
        engine.obtain_transcript(
            video_id="abc123",
            url="https://www.youtube.com/watch?v=abc123",
            language=None,
            whisper_model="small",
            force_whisper=False,
            work_dir=tmp_path,
            warnings=[],
        )


def test_whisper_unavailable_propagates_clear_error(monkeypatch, tmp_path):
    def fake_get_captions(video_id, preferred_language=None):
        raise CaptionsUnavailableError("no captions")

    def fake_download_audio(url, video_id, work_dir, **kwargs):
        return Path(work_dir) / f"{video_id}.wav"

    def fake_transcribe(*args, **kwargs):
        raise WhisperUnavailableError("faster-whisper is not installed.")

    monkeypatch.setattr(engine.captions_module, "get_captions", fake_get_captions)
    monkeypatch.setattr(engine.audio_module, "download_audio", fake_download_audio)
    monkeypatch.setattr(engine.whisper_engine, "transcribe_audio", fake_transcribe)

    with pytest.raises(WhisperUnavailableError):
        engine.obtain_transcript(
            video_id="abc123",
            url="https://www.youtube.com/watch?v=abc123",
            language=None,
            whisper_model="small",
            force_whisper=False,
            work_dir=tmp_path,
            warnings=[],
        )


def test_whisper_result_is_cached_and_reused(monkeypatch, tmp_path):
    def fake_get_captions(video_id, preferred_language=None):
        raise CaptionsUnavailableError("no captions")

    def fake_download_audio(url, video_id, work_dir, **kwargs):
        return Path(work_dir) / f"{video_id}.wav"

    whisper_result = TranscriptionResult(
        segments=[TranscriptSegment(start=0, end=1, text="hi")],
        source=TranscriptionSource.WHISPER,
        language="en",
        model="small",
    )
    transcribe_calls = []

    def fake_transcribe(*args, **kwargs):
        transcribe_calls.append(1)
        return whisper_result

    monkeypatch.setattr(engine.captions_module, "get_captions", fake_get_captions)
    monkeypatch.setattr(engine.audio_module, "download_audio", fake_download_audio)
    monkeypatch.setattr(engine.whisper_engine, "transcribe_audio", fake_transcribe)

    cache_dir = tmp_path / "cache"
    kwargs = dict(
        video_id="abc123",
        url="https://www.youtube.com/watch?v=abc123",
        language=None,
        whisper_model="small",
        force_whisper=False,
        work_dir=tmp_path / "audio",
        cache_dir=cache_dir,
    )

    first = engine.obtain_transcript(warnings=[], **kwargs)
    second = engine.obtain_transcript(warnings=[], **kwargs)

    assert len(transcribe_calls) == 1  # second call reused the cache instead of re-transcribing
    assert first.segments[0].text == second.segments[0].text == "hi"
    assert second.source == TranscriptionSource.WHISPER


def test_cache_is_scoped_per_model(monkeypatch, tmp_path):
    def fake_get_captions(video_id, preferred_language=None):
        raise CaptionsUnavailableError("no captions")

    def fake_download_audio(url, video_id, work_dir, **kwargs):
        return Path(work_dir) / f"{video_id}.wav"

    transcribe_calls = []

    def fake_transcribe(*args, **kwargs):
        transcribe_calls.append(kwargs.get("model_size"))
        return TranscriptionResult(
            segments=[TranscriptSegment(start=0, end=1, text="hi")],
            source=TranscriptionSource.WHISPER,
            language="en",
            model=kwargs.get("model_size"),
        )

    monkeypatch.setattr(engine.captions_module, "get_captions", fake_get_captions)
    monkeypatch.setattr(engine.audio_module, "download_audio", fake_download_audio)
    monkeypatch.setattr(engine.whisper_engine, "transcribe_audio", fake_transcribe)

    cache_dir = tmp_path / "cache"
    base_kwargs = dict(
        video_id="abc123",
        url="https://www.youtube.com/watch?v=abc123",
        language=None,
        force_whisper=False,
        work_dir=tmp_path / "audio",
        cache_dir=cache_dir,
    )

    engine.obtain_transcript(warnings=[], whisper_model="small", **base_kwargs)
    engine.obtain_transcript(warnings=[], whisper_model="medium", **base_kwargs)

    assert len(transcribe_calls) == 2  # different model => different cache key => no reuse
