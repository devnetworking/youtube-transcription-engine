"""Custom exceptions for the document processing module.

Mirrors src/exceptions.py: a flat hierarchy under one base class so
callers can catch `DocumentError` for anything "expected" (bad input,
corrupt PDF, missing pages) and let anything else surface as a bug.
"""

from __future__ import annotations


class DocumentError(Exception):
    """Base class for all expected, handled errors in this module."""


class InvalidUploadError(DocumentError):
    """The uploaded file failed MIME/magic-byte/size validation."""


class PathSecurityError(DocumentError):
    """A path escaped its expected root (path traversal / zip-slip)."""


class DocumentNotFoundError(DocumentError):
    pass


class JobNotFoundError(DocumentError):
    pass


class CorruptPDFError(DocumentError):
    """The PDF could not be opened/parsed by the PDF engine."""


class PageRangeError(DocumentError):
    """A page range expression was malformed or out of bounds."""


class OCRUnavailableError(DocumentError):
    """OCR was requested but no OCR engine/binary is installed."""


class ResourceLimitError(DocumentError):
    """A configured limit (size, pages, concurrent jobs) was exceeded."""


class JobCancelledError(DocumentError):
    """Raised internally to unwind a pipeline when a job is cancelled."""


class YouTubeError(DocumentError):
    """A YouTube-specific failure with an internal business code (section
    41): the message shown to the user is always human-readable; `code`
    (e.g. "YT_PRIVATE_VIDEO") is for logs/telemetry, never surfaced raw."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code
