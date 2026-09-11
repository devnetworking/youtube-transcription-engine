"""JSON exporters: metadata.json (mandatory context), and the optional
chapters.json / raw_transcript.json / processing_report.json artifacts
(spec sections 13 and 14).
"""

from __future__ import annotations

import json
from pathlib import Path

from ..models import Chapter, ProcessingReport, TranscriptSegment, VideoMetadata


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_metadata(path: Path, metadata: VideoMetadata) -> None:
    write_json(path, metadata.to_json_dict())


def write_processing_report(path: Path, report: ProcessingReport) -> None:
    write_json(path, report.to_json_dict())


def write_chapters(path: Path, chapters: list[Chapter]) -> None:
    write_json(path, {"chapters": [c.model_dump(mode="json") for c in chapters]})


def write_raw_transcript(path: Path, segments: list[TranscriptSegment]) -> None:
    write_json(path, {"segments": [s.model_dump(mode="json") for s in segments]})
