"""Untrusted-input validation: uploads, filenames, page range expressions.

Every PDF is treated as hostile content (section 31): we check magic
bytes ourselves rather than trusting the browser's Content-Type or the
file extension, and every page-range expression a user types is parsed
defensively with a specific, human-readable error instead of a stack
trace.
"""

from __future__ import annotations

import re

from .exceptions import InvalidUploadError, PageRangeError

_PDF_MAGIC = b"%PDF-"
_INVALID_DISPLAY_CHARS = re.compile(r'[\/\\:*?"<>|\r\n\t\x00-\x1f]')
_MAX_DISPLAY_NAME_LENGTH = 180


def sanitize_display_name(name: str | None, fallback: str = "document.pdf") -> str:
    """Clean a user-supplied filename for safe *display* and use in a
    Content-Disposition header. This is never used to build a filesystem
    path (see storage.py: paths are built from internal IDs only)."""
    candidate = (name or "").strip()
    if not candidate:
        candidate = fallback
    candidate = _INVALID_DISPLAY_CHARS.sub("_", candidate)
    candidate = candidate.strip(". ")
    if not candidate:
        candidate = fallback
    if len(candidate) > _MAX_DISPLAY_NAME_LENGTH:
        stem, _, ext = candidate.rpartition(".")
        keep = _MAX_DISPLAY_NAME_LENGTH - len(ext) - 1 if ext else _MAX_DISPLAY_NAME_LENGTH
        candidate = (stem[:keep] + "." + ext) if ext else candidate[:_MAX_DISPLAY_NAME_LENGTH]
    return candidate


def validate_pdf_header(head: bytes) -> None:
    """Check the first bytes of an upload against the PDF magic number.
    A `.pdf` extension or `application/pdf` Content-Type proves nothing
    on its own (section 31); this is what actually gates processing."""
    if not head.startswith(_PDF_MAGIC):
        raise InvalidUploadError(
            "This file does not look like a valid PDF (missing %PDF header). "
            "It may be corrupted, or not a PDF at all."
        )


def validate_extension(filename: str, allowed_extensions: list[str]) -> None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in {e.lower() for e in allowed_extensions}:
        raise InvalidUploadError(f"Files with extension '.{ext}' are not accepted. Allowed: PDF.")


_RANGE_TOKEN = re.compile(r"^(\d+)(?:-(\d+))?$")


def parse_page_ranges(spec: str, page_count: int) -> list[int]:
    """Parse a page-range expression like "1-5,8,10-20" into a sorted,
    de-duplicated list of 1-indexed page numbers, validated against the
    document's actual page count (section 53).

    Accepted: "1", "1-5", "1,3,5", "1-5,8,10-20".
    Rejected, each with a specific message: empty tokens ("3,,5"),
    non-numeric tokens ("abc"), zero/negative pages, an inverted range
    ("4-2"), and any page beyond `page_count`.
    """
    if not spec or not spec.strip():
        raise PageRangeError("Enter at least one page or page range, e.g. \"1-10\".")

    pages: set[int] = set()
    for raw_token in spec.split(","):
        token = raw_token.strip()
        if not token:
            raise PageRangeError(f"'{spec}' contains an empty entry between commas.")

        match = _RANGE_TOKEN.match(token)
        if not match:
            raise PageRangeError(f"'{token}' is not a valid page or page range.")

        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start

        if start == 0 or end == 0:
            raise PageRangeError("Page numbers start at 1 - '0' is not a valid page.")
        if start > end:
            raise PageRangeError(f"'{token}' is an inverted range (start page after end page).")
        if end > page_count:
            noun = "page" if page_count == 1 else "pages"
            raise PageRangeError(
                f"Pages {start}-{end} cannot be selected because the document contains only "
                f"{page_count} {noun}."
            )

        pages.update(range(start, end + 1))

    return sorted(pages)


def format_page_ranges(pages: list[int]) -> str:
    """Inverse of parse_page_ranges, for previewing a naming pattern or
    echoing back a normalized selection."""
    if not pages:
        return ""
    ordered = sorted(set(pages))
    groups: list[str] = []
    start = prev = ordered[0]
    for page in ordered[1:]:
        if page == prev + 1:
            prev = page
            continue
        groups.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = page
    groups.append(str(start) if start == prev else f"{start}-{prev}")
    return ",".join(groups)
