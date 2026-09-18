"""PDF engine abstraction, backed by PyMuPDF (fitz).

Kept as a thin wrapper (rather than calling `fitz` all over the
codebase) so the concrete engine can be swapped later (section 60)
without touching the pipeline, merge/split services, or tests - they
depend on the dataclasses below, not on PyMuPDF's own API shape.

PyMuPDF was chosen over a pure-text library (pypdf, pdfminer) because
Markdown reconstruction needs more than character extraction: per-span
font size/weight for heading detection, native table detection
(`page.find_tables`), page rendering for thumbnails/previews, and image
extraction, all from one library, without wiring together four
different ones for one document. It is used under the AGPL-3.0
license, which is stated here explicitly (section 59) rather than
buried - a commercial license from Artifex would be required to
distribute this as closed-source software; that's out of scope for
this local tool but worth knowing if it's ever packaged differently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pymupdf as fitz

from .exceptions import CorruptPDFError

_BOLD_FLAG = 1 << 4
_ITALIC_FLAG = 1 << 1


@dataclass
class TextSpan:
    text: str
    size: float
    bold: bool
    italic: bool
    font: str
    bbox: tuple[float, float, float, float]


@dataclass
class TextLine:
    spans: list[TextSpan]
    bbox: tuple[float, float, float, float]

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)


@dataclass
class TextBlock:
    lines: list[TextLine]
    bbox: tuple[float, float, float, float]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def max_size(self) -> float:
        return max((s.size for line in self.lines for s in line.spans), default=0.0)

    @property
    def is_bold(self) -> bool:
        spans = [s for line in self.lines for s in line.spans if s.text.strip()]
        return bool(spans) and all(s.bold for s in spans)


@dataclass
class TableData:
    bbox: tuple[float, float, float, float]
    rows: list[list[str]]


@dataclass
class LinkData:
    uri: str
    bbox: tuple[float, float, float, float]
    text: str = ""


@dataclass
class ImageData:
    data: bytes
    ext: str
    bbox: Optional[tuple[float, float, float, float]]


@dataclass
class PageLayout:
    page_index: int
    width: float
    height: float
    blocks: list[TextBlock] = field(default_factory=list)
    tables: list[TableData] = field(default_factory=list)
    links: list[LinkData] = field(default_factory=list)
    char_count: int = 0


class PDFDocument:
    """A single opened PDF, backed by a `fitz.Document`. Use as a
    context manager so the underlying file handle is always released."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self._doc = fitz.open(str(path))
        except Exception as exc:  # PyMuPDF raises its own RuntimeError/ValueError variants
            raise CorruptPDFError(
                f"The PDF appears to be corrupted and could not be opened ({exc})."
            ) from exc
        if self._doc.is_encrypted and not self._doc.authenticate(""):
            raise CorruptPDFError("This PDF is password-protected and cannot be processed.")

    def __enter__(self) -> "PDFDocument":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        self._doc.close()

    @property
    def page_count(self) -> int:
        return self._doc.page_count

    def has_extractable_text(self, sample_pages: int = 5) -> bool:
        """Heuristic used to decide whether OCR is needed (section 11):
        sample a handful of pages and check whether a meaningful amount
        of text is already extractable."""
        if self.page_count == 0:
            return True
        step = max(1, self.page_count // sample_pages)
        indices = list(range(0, self.page_count, step))[:sample_pages]
        total_chars = 0
        for i in indices:
            total_chars += len(self._doc[i].get_text("text").strip())
        return (total_chars / max(len(indices), 1)) > 20

    def get_page_layout(self, page_index: int) -> PageLayout:
        page = self._doc[page_index]
        raw = page.get_text("dict")
        layout = PageLayout(page_index=page_index, width=raw["width"], height=raw["height"])

        for raw_block in raw.get("blocks", []):
            if raw_block.get("type") != 0:  # 0 = text, 1 = image; images handled separately
                continue
            lines: list[TextLine] = []
            for raw_line in raw_block.get("lines", []):
                spans = [
                    TextSpan(
                        text=s["text"],
                        size=round(s["size"], 1),
                        bold=bool(s["flags"] & _BOLD_FLAG) or "bold" in s["font"].lower(),
                        italic=bool(s["flags"] & _ITALIC_FLAG) or "italic" in s["font"].lower(),
                        font=s["font"],
                        bbox=tuple(s["bbox"]),
                    )
                    for s in raw_line.get("spans", [])
                    if s["text"]
                ]
                if spans:
                    lines.append(TextLine(spans=spans, bbox=tuple(raw_line["bbox"])))
            if lines:
                layout.blocks.append(TextBlock(lines=lines, bbox=tuple(raw_block["bbox"])))

        layout.char_count = sum(len(b.text) for b in layout.blocks)

        if hasattr(page, "find_tables"):
            try:
                finder = page.find_tables()
                for table in finder.tables:
                    rows = table.extract()
                    cleaned = [[(cell or "").strip() for cell in row] for row in rows]
                    if any(any(cell for cell in row) for row in cleaned):
                        layout.tables.append(TableData(bbox=tuple(table.bbox), rows=cleaned))
            except Exception:
                pass  # Table detection is best-effort; never fail the page over it.

        for link in page.get_links():
            uri = link.get("uri")
            if uri:
                layout.links.append(LinkData(uri=uri, bbox=tuple(link.get("from", (0, 0, 0, 0)))))

        return layout

    def extract_page_images(self, page_index: int, min_dim: int = 60) -> list[ImageData]:
        """Images embedded in one page, skipping tiny decorative
        artifacts (bullets, rules) below `min_dim` pixels on both axes."""
        page = self._doc[page_index]
        images: list[ImageData] = []
        for img in page.get_images(full=True):
            xref = img[0]
            try:
                base = self._doc.extract_image(xref)
            except Exception:
                continue
            if base["width"] < min_dim or base["height"] < min_dim:
                continue
            bbox = None
            try:
                rects = page.get_image_rects(img)
                if rects:
                    bbox = tuple(rects[0])
            except Exception:
                pass
            images.append(ImageData(data=base["image"], ext=base["ext"], bbox=bbox))
        return images

    def render_thumbnail(self, page_index: int, max_dim: int = 320) -> bytes:
        page = self._doc[page_index]
        rect = page.rect
        scale = max_dim / max(rect.width, rect.height, 1)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        return pix.tobytes("png")

    def render_page_image(self, page_index: int, dpi: int = 300) -> bytes:
        """Higher-resolution render used as OCR input, where thumbnail
        resolution would hurt recognition accuracy."""
        page = self._doc[page_index]
        scale = dpi / 72
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        return pix.tobytes("png")


def open_pdf(path: Path) -> PDFDocument:
    return PDFDocument(path)


def _group_consecutive(pages: list[int]) -> list[tuple[int, int]]:
    """[0,1,2,5,6] -> [(0,2),(5,6)], used so merge/split can call
    insert_pdf once per contiguous run instead of once per page."""
    if not pages:
        return []
    runs: list[tuple[int, int]] = []
    start = prev = pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
            continue
        runs.append((start, prev))
        start = prev = p
    runs.append((start, prev))
    return runs


def merge_pdfs(sources: list[tuple[Path, Optional[list[int]]]], output_path: Path) -> int:
    """`sources` is a list of (path, 0-indexed page indices or None for
    all pages), in the desired output order. Returns the page count of
    the merged document."""
    merged = fitz.open()
    try:
        for path, page_indices in sources:
            with PDFDocument(path) as src:
                if page_indices is None:
                    merged.insert_pdf(src._doc)
                else:
                    for start, end in _group_consecutive(sorted(page_indices)):
                        merged.insert_pdf(src._doc, from_page=start, to_page=end)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        merged.save(str(output_path))
        return merged.page_count
    finally:
        merged.close()


def extract_pages(source: Path, page_indices: list[int], output_path: Path) -> int:
    """Write a new PDF containing exactly `page_indices` (0-indexed,
    order preserved as given) from `source`."""
    with PDFDocument(source) as src:
        out = fitz.open()
        try:
            for start, end in _group_consecutive(sorted(page_indices)):
                out.insert_pdf(src._doc, from_page=start, to_page=end)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            out.save(str(output_path))
            return out.page_count
        finally:
            out.close()
