"""YouTube caption retrieval (spec section 4, Priority 1 and 2).

Manually created captions are preferred over automatic ones. When no
target language is requested ("auto"), any manually created track wins
over any automatic track, regardless of language, per the "Priority
1/2" ordering in the spec (caption quality matters more than a language
preference we were never given).
"""

from __future__ import annotations

from typing import Optional

from ..exceptions import CaptionsUnavailableError, VideoUnavailableError
from ..models import TranscriptionResult, TranscriptionSource, TranscriptSegment


def list_available_languages(video_id: str) -> list[dict]:
    """List the caption tracks YouTube actually publishes for this video
    (section 16: never offer a language that isn't really there).
    Returns [] if captions are disabled/unavailable - that's a normal,
    expected outcome here (unlike get_captions, this never raises for
    "no captions", since it's used for a preview, not a transcription
    attempt)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return []

    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
    except Exception:  # noqa: BLE001 - any failure here just means "no languages to show"
        return []

    return [
        {"code": t.language_code, "name": t.language, "is_generated": t.is_generated}
        for t in transcript_list
    ]


def get_captions(video_id: str, preferred_language: Optional[str] = None) -> TranscriptionResult:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import (
            TranscriptsDisabled,
            NoTranscriptFound,
            VideoUnavailable,
            CouldNotRetrieveTranscript,
        )
    except ImportError as exc:  # pragma: no cover
        raise CaptionsUnavailableError("youtube-transcript-api is not installed.") from exc

    api = YouTubeTranscriptApi()

    try:
        transcript_list = api.list(video_id)
    except VideoUnavailable as exc:
        raise VideoUnavailableError(f"Video unavailable: {video_id}") from exc
    except TranscriptsDisabled as exc:
        raise CaptionsUnavailableError(f"Captions are disabled for video: {video_id}") from exc
    except CouldNotRetrieveTranscript as exc:
        raise CaptionsUnavailableError(f"Could not retrieve captions for {video_id}: {exc}") from exc

    transcript = _select_transcript(transcript_list, preferred_language)
    if transcript is None:
        raise CaptionsUnavailableError(f"No usable caption track found for video: {video_id}")

    try:
        fetched = transcript.fetch()
    except NoTranscriptFound as exc:
        raise CaptionsUnavailableError(f"No transcript found for {video_id}: {exc}") from exc
    except CouldNotRetrieveTranscript as exc:
        raise CaptionsUnavailableError(f"Could not fetch captions for {video_id}: {exc}") from exc

    segments = [
        TranscriptSegment(
            start=snippet.start,
            end=snippet.start + snippet.duration,
            text=snippet.text.strip(),
        )
        for snippet in fetched
        if snippet.text and snippet.text.strip()
    ]

    if not segments:
        raise CaptionsUnavailableError(f"Caption track for {video_id} was empty.")

    source = TranscriptionSource.AUTO_CAPTIONS if transcript.is_generated else TranscriptionSource.MANUAL_CAPTIONS

    return TranscriptionResult(
        segments=segments,
        source=source,
        language=transcript.language_code,
        model=None,
    )


def _select_transcript(transcript_list, preferred_language: Optional[str]):
    lang_wanted = preferred_language and preferred_language != "auto"

    if lang_wanted:
        candidates = [preferred_language]
        try:
            return transcript_list.find_manually_created_transcript(candidates)
        except Exception:  # noqa: BLE001 - fall through to generated/any-language
            pass
        try:
            return transcript_list.find_generated_transcript(candidates)
        except Exception:  # noqa: BLE001
            pass

    manual, generated = None, None
    for transcript in transcript_list:
        if transcript.is_generated and generated is None:
            generated = transcript
        elif not transcript.is_generated and manual is None:
            manual = transcript

    return manual or generated
