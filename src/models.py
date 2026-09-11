"""Structured data models shared across the pipeline.

Using Pydantic models (rather than loose dicts) gives us validation,
JSON (de)serialization for metadata.json / processing_report.json, and
a single source of truth for field names referenced throughout the
Markdown/TXT exporters.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TranscriptionSource(str, Enum):
    MANUAL_CAPTIONS = "Manual captions"
    AUTO_CAPTIONS = "Auto captions"
    WHISPER = "Whisper"


class QualityLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TranscriptSegment(BaseModel):
    start: float
    end: Optional[float] = None
    text: str
    uncertain: bool = False
    uncertain_reason: Optional[str] = None
    language: Optional[str] = None


class Chapter(BaseModel):
    index: int
    title: str
    timestamp_seconds: float
    source: str = "inferred"  # "youtube" or "inferred"


class VideoMetadata(BaseModel):
    video_id: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    channel: Optional[str] = None
    channel_url: Optional[str] = None
    publication_date: Optional[str] = None
    duration_seconds: Optional[int] = None
    detected_language: Optional[str] = None
    caption_language: Optional[str] = None
    transcription_source: Optional[str] = None
    transcription_model: Optional[str] = None
    processed_at: Optional[str] = None
    word_count: int = 0
    chapter_count: int = 0

    def to_json_dict(self) -> dict:
        return self.model_dump(mode="json")


class ProcessingReport(BaseModel):
    status: str = "pending"
    caption_source_found: bool = False
    audio_transcription_required: bool = False
    language_detection_confidence: Optional[str] = None
    uncertain_segments: int = 0
    quality: Optional[QualityLevel] = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def to_json_dict(self) -> dict:
        return self.model_dump(mode="json")


class TranscriptionResult(BaseModel):
    segments: list[TranscriptSegment]
    source: TranscriptionSource
    language: Optional[str] = None
    model: Optional[str] = None
    low_confidence_language: bool = False


class VideoOutcome(BaseModel):
    """Result of running the pipeline for a single video, shared by the
    CLI and the web UI so both surfaces report the same information."""

    success: bool
    video_dir: Optional[str] = None
    title: Optional[str] = None
    quality: Optional[QualityLevel] = None
    source: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    summary: str = ""
    key_topics: list[str] = Field(default_factory=list)
    key_terms: dict[str, str] = Field(default_factory=dict)
    chapters: list[Chapter] = Field(default_factory=list)
    takeaways: list[str] = Field(default_factory=list)
    resources: dict[str, list[str]] = Field(default_factory=dict)
    questions: list[str] = Field(default_factory=list)
    notes: dict[str, list[str]] = Field(default_factory=dict)
    research: dict[str, list[str]] = Field(default_factory=dict)
