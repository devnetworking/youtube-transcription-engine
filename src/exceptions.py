"""Custom exceptions for the transcription engine.

Keeping these distinct (rather than raising bare Exception/ValueError)
lets the CLI produce clear, specific error messages per video instead of
a generic traceback, and lets callers distinguish "expected" failures
(private video, no captions) from bugs.
"""

from __future__ import annotations


class TranscriptionError(Exception):
    """Base class for all expected, handled errors in this project."""


class InvalidURLError(TranscriptionError):
    pass


class VideoUnavailableError(TranscriptionError):
    pass


class PrivateVideoError(TranscriptionError):
    pass


class AgeRestrictedError(TranscriptionError):
    pass


class NetworkError(TranscriptionError):
    pass


class MetadataFetchError(TranscriptionError):
    pass


class CaptionsUnavailableError(TranscriptionError):
    pass


class AudioExtractionError(TranscriptionError):
    pass


class FFmpegNotFoundError(AudioExtractionError):
    pass


class WhisperUnavailableError(TranscriptionError):
    """faster-whisper (or its dependencies) is not installed."""


class WhisperModelError(TranscriptionError):
    pass


class InsufficientMemoryError(TranscriptionError):
    pass


class NoTranscriptionSourceError(TranscriptionError):
    """Neither captions nor audio transcription produced usable text."""


class OutputValidationError(TranscriptionError):
    pass
