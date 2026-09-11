"""Audio extraction for the Whisper fallback path (spec section 4, Priority 3)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

from ..exceptions import AudioExtractionError, FFmpegNotFoundError
from .metadata import SilentYtDlpLogger


def check_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def download_audio(
    url: str,
    video_id: str,
    work_dir: Path,
    verbose: bool = False,
    report: Optional[Callable[[str], None]] = None,
) -> Path:
    """Download and extract the best-available audio track to a WAV file.

    Returns the path to the extracted audio. Raises FFmpegNotFoundError
    if ffmpeg is missing (yt-dlp needs it to convert to a decodable
    format for faster-whisper).
    """
    if not check_ffmpeg_available():
        raise FFmpegNotFoundError(
            "ffmpeg was not found on PATH. It is required to extract audio "
            "for local speech-to-text transcription. Install ffmpeg and "
            "ensure it is on PATH, or rely on YouTube captions instead."
        )

    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover
        raise AudioExtractionError("yt-dlp is not installed.") from exc

    work_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(work_dir / f"{video_id}.%(ext)s")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "logger": SilentYtDlpLogger(verbose=verbose, sink=report),
        "color": "no_color",
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }
        ],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as exc:  # noqa: BLE001 - normalize any yt-dlp/ffmpeg failure
        raise AudioExtractionError(f"Failed to extract audio for {url}: {exc}") from exc

    audio_path = work_dir / f"{video_id}.wav"
    if not audio_path.exists():
        raise AudioExtractionError(f"Audio extraction did not produce an output file for {url}")

    return audio_path
