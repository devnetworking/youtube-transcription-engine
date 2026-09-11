"""The end-to-end per-video pipeline, shared by the CLI (`cli.py`) and
the local web UI (`webapp.py`) so both surfaces run identical logic and
only differ in how progress/results are presented (spec section 29:
avoid duplicated logic).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from .analysis.chapters import chapters_from_youtube, infer_chapters
from .analysis.enrich import extract_resources, generate_questions, research_mode_analysis
from .analysis.keywords import extract_key_terms_with_context, extract_keywords
from .analysis.quality import compute_quality
from .analysis.summary import generate_summary, generate_takeaways
from .config import AppConfig
from .exceptions import TranscriptionError
from .exporters.blocks import group_by_chapter
from .exporters.json_exporter import (
    write_chapters,
    write_metadata,
    write_processing_report,
    write_raw_transcript,
)
from .exporters.markdown_exporter import build_markdown
from .exporters.text_exporter import build_text
from .models import AnalysisResult, ProcessingReport, VideoOutcome
from .transcription.cleanup import clean_segments
from .transcription.engine import obtain_transcript
from .utils.filenames import unique_output_dir
from .utils.validation import validate_output
from .youtube.metadata import expand_playlist, fetch_metadata, is_playlist_url

ReportFn = Callable[[str, str], None]  # (message, level) where level is
# one of "step", "info", "success", "warning", "error".


def _default_report(_message: str, _level: str) -> None:
    pass


def resolve_urls(urls: list[str], report: Optional[ReportFn] = None, verbose: bool = False) -> list[str]:
    """Expand any playlist URLs in `urls` into their individual video
    URLs (spec section 2: "a playlist URL when feasible"); anything
    that isn't a playlist URL passes through unchanged.
    """
    report = report or _default_report
    resolved: list[str] = []

    for url in urls:
        if not is_playlist_url(url):
            resolved.append(url)
            continue

        report(f"Playlist detected, expanding: {url}", "info")
        try:
            expansion = expand_playlist(url, verbose=verbose)
        except TranscriptionError as exc:
            report(f"Failed to expand playlist {url}: {exc}", "error")
            continue

        report(f"Playlist expanded to {len(expansion.urls)} video(s).", "info")
        if expansion.truncated:
            report(
                f"Playlist has {expansion.total_found} videos; only the first "
                f"{len(expansion.urls)} will be processed.",
                "warning",
            )
        resolved.extend(expansion.urls)

    return resolved


def process_video(
    url: str,
    config: AppConfig,
    output_root: Path,
    report: Optional[ReportFn] = None,
) -> VideoOutcome:
    report = report or _default_report
    processing_report = ProcessingReport(status="pending")

    def notify(msg: str) -> None:
        report(msg, "step")

    report(f"Processing: {url}", "info")
    try:
        report("[1/6] Reading YouTube metadata...", "step")
        metadata, raw_info = fetch_metadata(url, verbose=config.verbose, report=notify)
    except TranscriptionError as exc:
        report(f"Failed to read video metadata: {exc}", "error")
        return VideoOutcome(success=False, errors=[str(exc)])

    video_dir = unique_output_dir(output_root, metadata.title, metadata.video_id)
    audio_work_dir = output_root / ".cache" / "audio"
    transcript_cache_dir = output_root / ".cache" / "transcripts"

    if config.diarize:
        processing_report.warnings.append(
            "Diarization was requested but is not available in this build; speaker labels were omitted."
        )

    report(
        "[2/6] Searching captions..." if config.prefer_captions and not config.force_whisper
        else "[2/6] Skipping captions (--force-whisper)...",
        "step",
    )
    try:
        result = obtain_transcript(
            video_id=metadata.video_id,
            url=metadata.url,
            language=None if config.language == "auto" else config.language,
            whisper_model=config.whisper_model,
            force_whisper=config.force_whisper or not config.prefer_captions,
            work_dir=audio_work_dir,
            warnings=processing_report.warnings,
            notify=notify,
            verbose=config.verbose,
            cache_dir=transcript_cache_dir,
        )
    except TranscriptionError as exc:
        report(f"Transcription failed: {exc}", "error")
        processing_report.status = "failed"
        processing_report.errors.append(str(exc))
        return VideoOutcome(success=False, title=metadata.title, errors=[str(exc)], warnings=processing_report.warnings)

    processing_report.caption_source_found = result.source.value != "Whisper"
    processing_report.audio_transcription_required = result.source.value == "Whisper"

    report("[5/6] Cleaning and structuring transcript...", "step")
    cleaned_segments = clean_segments(result.segments, remove_filler_words=config.remove_filler_words)
    if not cleaned_segments:
        report("Transcript was empty after cleaning; refusing to write empty output.", "error")
        return VideoOutcome(success=False, title=metadata.title, errors=["Transcript was empty after cleaning."])

    processing_report.uncertain_segments = sum(1 for s in cleaned_segments if s.uncertain)
    if result.low_confidence_language:
        processing_report.language_detection_confidence = "low"

    raw_chapters = chapters_from_youtube(raw_info.get("chapters")) if config.chapter_detection else []
    chapters = raw_chapters if raw_chapters else (
        infer_chapters(cleaned_segments, language=result.language) if config.chapter_detection else []
    )

    full_text = " ".join(s.text for s in cleaned_segments)

    analysis = AnalysisResult()
    if config.generate_summary:
        analysis.summary = generate_summary(full_text, language=result.language)
        analysis.takeaways = generate_takeaways(full_text, language=result.language)
    analysis.key_topics = extract_keywords(full_text, top_n=8, language=result.language)
    analysis.key_terms = extract_key_terms_with_context(full_text, language=result.language)
    analysis.resources = extract_resources(full_text)
    analysis.questions = generate_questions(analysis.key_topics)
    if config.research_mode:
        analysis.research = research_mode_analysis(full_text, language=result.language)

    quality = compute_quality(result)
    processing_report.quality = quality

    metadata.detected_language = result.language
    metadata.caption_language = result.language if result.source.value != "Whisper" else None
    metadata.transcription_source = result.source.value
    metadata.transcription_model = result.model
    metadata.word_count = sum(len(s.text.split()) for s in cleaned_segments)
    metadata.chapter_count = len(chapters)

    sections = group_by_chapter(cleaned_segments, chapters)

    report("[6/6] Writing transcript.md and transcript.txt...", "step")
    try:
        video_dir.mkdir(parents=True, exist_ok=True)
        md_path = video_dir / "transcript.md"
        txt_path = video_dir / "transcript.txt"

        md_path.write_text(
            build_markdown(metadata, sections, analysis, processing_report, include_timestamps=config.timestamps),
            encoding="utf-8",
        )
        txt_path.write_text(build_text(metadata, sections, include_timestamps=config.timestamps), encoding="utf-8")

        if config.generate_metadata:
            write_metadata(video_dir / "metadata.json", metadata)
        write_processing_report(video_dir / "processing_report.json", processing_report)
        if chapters:
            write_chapters(video_dir / "chapters.json", chapters)
        write_raw_transcript(video_dir / "raw_transcript.json", cleaned_segments)
    except OSError as exc:
        report(f"Failed to write output files: {exc}", "error")
        return VideoOutcome(success=False, title=metadata.title, errors=[str(exc)])

    issues = validate_output(md_path, txt_path, metadata, cleaned_segments)
    if issues:
        processing_report.status = "failed"
        processing_report.errors.extend(issues)
        write_processing_report(video_dir / "processing_report.json", processing_report)
        report("Output validation failed:", "error")
        for issue in issues:
            report(f"  - {issue}", "error")
        return VideoOutcome(success=False, title=metadata.title, errors=issues)

    processing_report.status = "success"
    write_processing_report(video_dir / "processing_report.json", processing_report)

    report(f"Complete -> {video_dir}", "success")
    report(f"Transcription quality: {quality.value}  (source: {result.source.value})", "success")
    for warning in processing_report.warnings:
        report(f"warning: {warning}", "warning")

    return VideoOutcome(
        success=True,
        video_dir=str(video_dir),
        title=metadata.title,
        quality=quality,
        source=result.source.value,
        warnings=processing_report.warnings,
    )
