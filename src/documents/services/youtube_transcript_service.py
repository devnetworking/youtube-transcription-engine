"""YouTube Transcript, as a Documents job (sections 5-9, 19-22, 37-39).

Reuses the existing transcription engine wholesale - src/pipeline.py's
`process_video`/`resolve_urls`, src/youtube/metadata.py, src/youtube/
captions.py - rather than re-implementing URL parsing, metadata
fetching, the caption/Whisper fallback, or Markdown generation. This
service only adds the wiring needed to run that pipeline as a
Documents job: mapping its progress messages onto named stages,
writing outputs under this job's storage folder, and registering the
resulting transcript.md as a browsable Document (source=YOUTUBE) so it
shows up in Files/Search next to uploaded PDFs.
"""

from __future__ import annotations

import hashlib
import re
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from ...config import AppConfig
from ...exceptions import (
    AgeRestrictedError,
    InvalidURLError,
    MetadataFetchError,
    NetworkError,
    PrivateVideoError,
    TranscriptionError,
    VideoUnavailableError,
)
from ...pipeline import process_video, resolve_urls
from ...youtube.captions import list_available_languages
from ...youtube.metadata import expand_playlist, extract_video_id, fetch_metadata, is_playlist_url, normalize_url
from ..config import DocumentSettings
from ..exceptions import DocumentError, YouTubeError
from ..job_queue import CancelToken, JobTarget
from ..models import (
    Document,
    DocumentJob,
    DocumentOutput,
    DocumentSource,
    DocumentStatus,
    JobOperation,
    OutputType,
    PipelineStage,
    YouTubeTranscriptOptions,
)
from ..repository import DocumentRepository, now_iso
from ..storage import OUTPUTS, StorageProvider

STAGE_DEFS = [
    ("metadata", "Reading video metadata"),
    ("captions", "Searching captions"),
    ("transcript", "Obtaining transcript"),
    ("cleaning", "Cleaning transcript"),
    ("analysis", "Structuring content"),
    ("export", "Writing output files"),
]

_STEP_RE = re.compile(r"^\[(\d+)/6\]")
_STEP_TO_STAGE = {1: "metadata", 2: "captions", 5: "cleaning", 6: "export"}
_STAGE_PROGRESS = {
    "metadata": 0.05, "captions": 0.2, "transcript": 0.45,
    "cleaning": 0.7, "analysis": 0.85, "export": 0.95,
}
_OUTPUT_FILES = [
    ("transcript.md", OutputType.MARKDOWN),
    ("transcript.txt", OutputType.TEXT),
    ("metadata.json", OutputType.METADATA),
    ("chapters.json", OutputType.METADATA),
    ("processing_report.json", OutputType.METADATA),
    ("raw_transcript.json", OutputType.METADATA),
]


def _stage_for_message(message: str) -> Optional[str]:
    match = _STEP_RE.match(message)
    if match:
        return _STEP_TO_STAGE.get(int(match.group(1)))
    lowered = message.lower()
    if any(hint in lowered for hint in ("extracting audio", "transcribing with whisper", "cached whisper")):
        return "transcript"
    return None


class YouTubeTranscriptService:
    def __init__(self, storage: StorageProvider, repository: DocumentRepository, settings: DocumentSettings):
        self.storage = storage
        self.repository = repository
        self.settings = settings

    def preview(self, url: str) -> dict:
        """Metadata-only lookup for the "Video Preview" card (section 9) -
        never downloads audio/video, so pasting a URL to look at it never
        does the expensive part of the work (section 39)."""
        if is_playlist_url(url):
            try:
                expansion = expand_playlist(url)
            except TranscriptionError as exc:
                raise YouTubeError(
                    "We couldn't read this playlist. It may be private or unavailable.", code="YT_PROVIDER_ERROR"
                ) from exc
            return {
                "is_playlist": True,
                "video_count": len(expansion.urls),
                "total_found": expansion.total_found,
                "truncated": expansion.truncated,
            }

        try:
            video_id = extract_video_id(url)
            canonical = normalize_url(url)
        except InvalidURLError as exc:
            raise YouTubeError("This doesn't look like a valid YouTube URL.", code="YT_INVALID_URL") from exc

        try:
            metadata, raw_info = fetch_metadata(canonical)
        except PrivateVideoError as exc:
            raise YouTubeError("This video is private and can't be accessed.", code="YT_PRIVATE_VIDEO") from exc
        except AgeRestrictedError as exc:
            raise YouTubeError("This video is age-restricted and can't be accessed.", code="YT_AGE_RESTRICTED") from exc
        except VideoUnavailableError as exc:
            raise YouTubeError("We couldn't find this video - it may have been removed.", code="YT_VIDEO_NOT_FOUND") from exc
        except NetworkError as exc:
            raise YouTubeError("Couldn't reach YouTube - check your connection and try again.", code="YT_NETWORK_ERROR") from exc
        except MetadataFetchError as exc:
            raise YouTubeError("We couldn't read this video's information.", code="YT_PROVIDER_ERROR") from exc

        languages = list_available_languages(video_id)
        return {
            "is_playlist": False,
            "video_id": video_id,
            "url": canonical,
            "title": metadata.title,
            "channel": metadata.channel,
            "channel_url": metadata.channel_url,
            "duration_seconds": metadata.duration_seconds,
            "publication_date": metadata.publication_date,
            "thumbnail": raw_info.get("thumbnail"),
            "languages": languages,
            "captions_available": bool(languages),
        }

    def create_jobs(self, options: YouTubeTranscriptOptions) -> list[DocumentJob]:
        video_urls = resolve_urls([options.url])
        if not video_urls:
            raise YouTubeError("Could not resolve any video from that URL.", code="YT_INVALID_URL")

        jobs: list[DocumentJob] = []
        for video_url in video_urls:
            stages = [PipelineStage(key=k, label=label) for k, label in STAGE_DEFS]
            job_options = options.model_dump()
            job_options["url"] = video_url
            job = DocumentJob(
                id=uuid.uuid4().hex,
                operation=JobOperation.YOUTUBE_TRANSCRIPT,
                stages=stages,
                input_document_ids=[],
                options=job_options,
                created_at=now_iso(),
            )
            self.repository.create_job(job)
            jobs.append(job)

        self.repository.audit("YOUTUBE_TRANSCRIPT_QUEUED", jobs[0].id if jobs else None, options.url)
        return jobs

    def build_target(self, job: DocumentJob) -> JobTarget:
        options = YouTubeTranscriptOptions(**job.options)

        def target(token: CancelToken) -> None:
            stages = [PipelineStage(**s.model_dump()) for s in job.stages]
            config = AppConfig(
                language=options.language,
                whisper_model=options.whisper_model,
                force_whisper=options.force_whisper,
                prefer_captions=not options.force_whisper,
                timestamps=options.timestamps,
                chapter_detection=options.chapter_detection,
                generate_summary=options.generate_summary,
                generate_txt=options.generate_txt,
                generate_metadata=options.generate_metadata,
                research_mode=options.research_mode,
                remove_filler_words=options.remove_filler_words,
            )

            output_root = self.storage.abs_path(f"{OUTPUTS}/{job.id}")

            def report(message: str, level: str) -> None:
                self.repository.append_job_log(job.id, message, level)
                stage_key = _stage_for_message(message)
                if stage_key:
                    token.set_stage(stages, stage_key, _STAGE_PROGRESS[stage_key])
                token.check()

            token.set_stage(stages, "metadata", 0.02)
            outcome = process_video(options.url, config, output_root, report=report)

            if not outcome.success:
                raise DocumentError("; ".join(outcome.errors) or "Transcription failed.")

            video_dir_name = Path(outcome.video_dir).name
            video_dir = output_root / video_dir_name

            outputs_created: list[DocumentOutput] = []
            for filename, output_type in _OUTPUT_FILES:
                file_path = video_dir / filename
                if not file_path.exists():
                    continue
                storage_key = f"{OUTPUTS}/{job.id}/{video_dir_name}/{filename}"
                outputs_created.append(DocumentOutput(
                    id=uuid.uuid4().hex, job_id=job.id, output_type=output_type,
                    storage_key=storage_key, filename=filename,
                    file_size=file_path.stat().st_size, created_at=now_iso(),
                ))

            zip_path = video_dir / "package.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for path in video_dir.iterdir():
                    if path.is_file() and path.name != "package.zip":
                        zf.write(path, arcname=path.name)
            outputs_created.append(DocumentOutput(
                id=uuid.uuid4().hex, job_id=job.id, output_type=OutputType.ZIP,
                storage_key=f"{OUTPUTS}/{job.id}/{video_dir_name}/package.zip", filename="package.zip",
                file_size=zip_path.stat().st_size, created_at=now_iso(),
            ))

            for output in outputs_created:
                self.repository.create_output(output)

            md_path = video_dir / "transcript.md"
            if md_path.exists():
                md_bytes = md_path.read_bytes()
                document = Document(
                    id=uuid.uuid4().hex,
                    original_name=f"{outcome.title or video_dir_name}.md",
                    storage_key=f"{OUTPUTS}/{job.id}/{video_dir_name}/transcript.md",
                    mime_type="text/markdown",
                    file_size=len(md_bytes),
                    checksum_sha256=hashlib.sha256(md_bytes).hexdigest(),
                    status=DocumentStatus.READY,
                    source=DocumentSource.YOUTUBE,
                    source_job_id=job.id,
                    created_at=now_iso(),
                )
                self.repository.create_document(document)
                self.repository.audit("DOCUMENT_GENERATED", document.id, "youtube transcript")

            token.set_stage(stages, "export", 1.0)
            token.finish_stages(stages)
            self.repository.update_job(job.id, result_summary={
                "title": outcome.title,
                "quality": outcome.quality.value if outcome.quality else None,
                "source": outcome.source,
                "warnings": outcome.warnings,
            })
            self.repository.audit("YOUTUBE_TRANSCRIPT_CREATED", job.id, outcome.title or video_dir_name)

        return target
