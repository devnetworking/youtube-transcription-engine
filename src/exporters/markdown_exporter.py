"""Markdown exporter (spec section 11)."""

from __future__ import annotations

from ..models import AnalysisResult, ProcessingReport, VideoMetadata
from ..utils.timestamps import format_timestamp
from .blocks import ChapterSection


def build_markdown(
    metadata: VideoMetadata,
    sections: list[ChapterSection],
    analysis: AnalysisResult,
    report: ProcessingReport,
    include_timestamps: bool = True,
) -> str:
    parts: list[str] = []

    title = metadata.title or "Untitled Video"
    parts.append(f"# {title}\n")

    parts.append(_video_information(metadata))

    if analysis.summary:
        parts.append(f"## Executive Summary\n\n{analysis.summary}\n")

    if analysis.key_topics:
        topics = "\n".join(f"- {t}" for t in analysis.key_topics)
        parts.append(f"## Key Topics\n\n{topics}\n")

    if analysis.key_terms:
        rows = "\n".join(f"| {term} | {context} |" for term, context in analysis.key_terms.items())
        parts.append(f"## Key Concepts and Terms\n\n| Term | Context |\n|---|---|\n{rows}\n")

    if sections:
        if include_timestamps:
            chapter_lines = "\n".join(
                f"{i}. `{format_timestamp(s.chapter.timestamp_seconds)}` — {s.chapter.title}"
                for i, s in enumerate(sections, start=1)
            )
        else:
            chapter_lines = "\n".join(f"{i}. {s.chapter.title}" for i, s in enumerate(sections, start=1))
        parts.append(f"## Chapters\n\n{chapter_lines}\n")

    parts.append("---\n")
    parts.append("# Full Transcript\n")
    parts.append(_transcript_body(sections, include_timestamps))
    parts.append("---\n")

    if analysis.takeaways:
        items = "\n".join(f"- {t}" for t in analysis.takeaways)
        parts.append(f"## Important Takeaways\n\n{items}\n")

    if analysis.resources:
        resource_lines = []
        for category, items in analysis.resources.items():
            resource_lines.append(f"**{category}:**")
            resource_lines.extend(f"- {item}" for item in items)
        parts.append("## Mentioned Resources\n\n" + "\n".join(resource_lines) + "\n")

    if analysis.questions:
        items = "\n".join(f"- {q}" for q in analysis.questions)
        parts.append(f"## Questions or Research Leads\n\n{items}\n")

    if analysis.research:
        titles = {
            "research_question": "Research Question",
            "hypotheses": "Hypotheses",
            "methodology": "Methodology",
            "datasets": "Datasets",
            "algorithms": "Algorithms/Models",
            "metrics": "Metrics",
            "limitations": "Limitations",
            "future_work": "Future Work",
            "citations": "Citations",
        }
        research_parts = ["## Research Mode Analysis\n"]
        for key, sentences in analysis.research.items():
            heading = titles.get(key, key.replace("_", " ").title())
            research_parts.append(f"**{heading}:**")
            research_parts.extend(f"- {s}" for s in sentences)
        parts.append("\n".join(research_parts) + "\n")

    notes = _transcription_notes(report, analysis)
    if notes:
        parts.append(notes)

    return "\n".join(parts).strip() + "\n"


def _video_information(metadata: VideoMetadata) -> str:
    duration = format_timestamp(metadata.duration_seconds) if metadata.duration_seconds else "Unknown"
    lines = [
        "## Video Information\n",
        f"- **URL:** {metadata.url or 'Unknown'}",
        f"- **Channel:** {metadata.channel or 'Unknown'}",
        f"- **Published:** {metadata.publication_date or 'Unknown'}",
        f"- **Duration:** {duration}",
        f"- **Language:** {metadata.detected_language or 'Unknown'}",
        f"- **Transcription source:** {metadata.transcription_source or 'Unknown'}",
        f"- **Processed on:** {metadata.processed_at or 'Unknown'}",
        "",
    ]
    return "\n".join(lines)


def _transcript_body(sections: list[ChapterSection], include_timestamps: bool = True) -> str:
    parts = []
    for i, section in enumerate(sections, start=1):
        parts.append(f"## {i}. {section.chapter.title}")
        if include_timestamps:
            parts.append(f"**Timestamp:** {format_timestamp(section.chapter.timestamp_seconds)}\n")
        for block in section.blocks:
            prefix = f"[{format_timestamp(block.start_seconds)}] " if include_timestamps else ""
            if block.is_code:
                parts.append(f"{prefix}*(reconstructed from speech)*\n```bash\n{block.text}\n```\n")
            else:
                parts.append(f"{prefix}{block.text}\n")
    return "\n".join(parts)


def _transcription_notes(report: ProcessingReport, analysis: AnalysisResult) -> str:
    lines = []
    if report.uncertain_segments:
        lines.append(f"- Unclear passages: {report.uncertain_segments} segment(s) marked uncertain/inaudible.")
    for category, items in analysis.notes.items():
        for item in items:
            lines.append(f"- {category}: {item}")
    if report.warnings:
        for warning in report.warnings:
            lines.append(f"- {warning}")

    if not lines:
        return ""
    return "## Transcription Notes\n\n" + "\n".join(lines) + "\n"
