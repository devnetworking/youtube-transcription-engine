"""Structured data models for the document processing module.

Pydantic models, matching the convention in src/models.py: a single
source of truth for field names, validation, and JSON (de)serialization
for the API responses.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    UPLOADING = "uploading"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class DocumentSource(str, Enum):
    """Where a Document's bytes came from (section 34) - lets the Files
    library and contextual actions distinguish an uploaded original from
    something the platform generated itself, without needing a separate
    storage system per source."""

    UPLOAD = "upload"
    YOUTUBE = "youtube"
    GENERATED = "generated"
    MERGE = "merge"
    SPLIT = "split"
    CONVERSION = "conversion"


class JobOperation(str, Enum):
    PDF_TO_MARKDOWN = "pdf_to_markdown"
    MERGE = "merge"
    SPLIT = "split"
    YOUTUBE_TRANSCRIPT = "youtube_transcript"


class JobStatus(str, Enum):
    QUEUED = "queued"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutputType(str, Enum):
    MARKDOWN = "markdown"
    TEXT = "text"
    METADATA = "metadata"
    ASSET = "asset"
    PDF = "pdf"
    ZIP = "zip"


class PipelineStage(BaseModel):
    """One step of a job's processing pipeline (section 22, 76)."""

    key: str
    label: str
    status: str = "waiting"  # waiting | running | done | skipped | failed


class Document(BaseModel):
    id: str
    original_name: str
    storage_key: str
    mime_type: str
    file_size: int
    page_count: Optional[int] = None
    checksum_sha256: Optional[str] = None
    status: DocumentStatus = DocumentStatus.READY
    source: DocumentSource = DocumentSource.UPLOAD
    source_job_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    deleted_at: Optional[str] = None


class LogEntry(BaseModel):
    """One line of a job's raw progress log (section 19 of the original
    YouTube tool's UI): kept generic on DocumentJob rather than only on
    the YouTube operation, since any future long-running operation can
    reuse it the same way."""

    message: str
    level: str = "info"  # step | info | success | warning | error
    at: str


class DocumentJob(BaseModel):
    id: str
    operation: JobOperation
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    stage: Optional[str] = None
    stages: list[PipelineStage] = Field(default_factory=list)
    logs: list[LogEntry] = Field(default_factory=list)
    input_document_ids: list[str] = Field(default_factory=list)
    options: dict = Field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    result_summary: dict = Field(default_factory=dict)
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class DocumentOutput(BaseModel):
    id: str
    job_id: str
    output_type: OutputType
    storage_key: str
    filename: str
    file_size: int
    created_at: str


class ConversionOptions(BaseModel):
    """Options panel for PDF -> Markdown (section 12)."""

    detect_headings: bool = True
    preserve_lists: bool = True
    detect_tables: bool = True
    extract_links: bool = True
    preserve_page_references: bool = True
    extract_images: bool = True
    ignore_decorative_images: bool = False
    ocr_mode: str = "auto"  # "auto" | "always" | "never"
    language: str = "auto"
    generate_txt: bool = False
    generate_metadata: bool = True
    export_assets: bool = True


class MergeInput(BaseModel):
    document_id: str
    page_ranges: Optional[str] = None  # e.g. "1-10,15" ; None = all pages


class MergeOptions(BaseModel):
    inputs: list[MergeInput]
    output_name: Optional[str] = None


class SplitMode(str, Enum):
    RANGES = "ranges"
    EVERY_N_PAGES = "every_n_pages"
    EXTRACT_PAGES = "extract_pages"
    EVERY_PAGE = "every_page"


class SplitOptions(BaseModel):
    document_id: str
    mode: SplitMode
    ranges: Optional[str] = None  # RANGES / EXTRACT_PAGES: "1-10,11-30" or "1,3,4,8,10-20"
    every_n_pages: Optional[int] = None
    naming_pattern: str = "{original_name}_part-{index}_pages-{start_page}-{end_page}"


class YouTubeTranscriptOptions(BaseModel):
    """Mirrors AppConfig's transcription-relevant fields (src/config.py)
    rather than re-declaring the whole pipeline's options - only what
    the Documents UI actually exposes for this operation."""

    url: str
    language: str = "auto"
    whisper_model: str = "auto"
    force_whisper: bool = False
    timestamps: bool = True
    chapter_detection: bool = True
    generate_summary: bool = True
    research_mode: bool = False
    remove_filler_words: bool = False
    generate_txt: bool = True
    generate_metadata: bool = True


class ConversionMetadata(BaseModel):
    """Per-conversion metadata (section 15), kept out of the main UI and
    surfaced only in a "Details" view."""

    source_file: str
    pages: int
    processing_time_seconds: float
    ocr_used: bool
    images_extracted: int
    tables_detected: int
    conversion_engine: str
    created_at: str
