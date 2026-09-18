"""Structural reconstruction of a PDF into typed content blocks
(sections 6-9): reading-order recovery for multi-column pages, heading
levels inferred from the font-size distribution, list/code/quote
detection, and merging in tables/images at their real position in the
flow - so the exporter in markdown_builder.py never has to guess, it
just renders whatever `analyze_document` already classified.

Every heuristic here only *classifies* text PyMuPDF already extracted;
none of it invents or rewrites content (section 2, 6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterator, Optional

from .pdf_engine import ImageData, LinkData, PDFDocument, TableData, TextBlock, TextSpan

_BULLET_RE = re.compile(r"^\s*[•‣◦▪·∙-]\s+")
# Optional leading "(" so "1.", "1)" and "(1)" (all common in real documents,
# especially "(a)"/"(i)" sub-items) are recognized as the same kind of marker.
_NUMBERED_RE = re.compile(r"^\s*\(?(\d{1,3}|[a-zA-Z]|[ivxlcdmIVXLCDM]{1,6})[.)]\s+")
_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")
_MONOSPACE_HINTS = ("mono", "courier", "consolas", "menlo", "inconsolata")


@dataclass
class DocBlock:
    kind: str  # heading | paragraph | list_item | table | image | code | quote
    page_index: int
    bbox: tuple[float, float, float, float]
    text: str = ""
    level: int = 1
    ordered: bool = False
    rows: Optional[list[list[str]]] = None
    image: Optional[ImageData] = None
    ocr_source: bool = False


def _reading_order(items: list[tuple[tuple[float, float, float, float], object]], page_width: float) -> list[object]:
    """Order `items` (bbox, payload) top-to-bottom, recovering left-then
    -right column order instead of interleaving lines from two columns
    (section 8). A "full-width" item (title, table, banner image) is
    treated as a column break: whatever narrow items came before it on
    each side are flushed in column-major order, then it is emitted,
    and column detection restarts below it.
    """
    if len(items) <= 1:
        return [payload for _, payload in items]

    narrow_threshold = 0.62 * page_width
    narrow_x0s = sorted(bbox[0] for bbox, _ in items if (bbox[2] - bbox[0]) <= narrow_threshold)

    split_x: Optional[float] = None
    if len(narrow_x0s) >= 2:
        gaps = [
            (narrow_x0s[i + 1] - narrow_x0s[i], narrow_x0s[i], narrow_x0s[i + 1])
            for i in range(len(narrow_x0s) - 1)
        ]
        best = max(gaps, key=lambda g: g[0], default=(0, 0, 0))
        if best[0] > 0.08 * page_width:
            split_x = (best[1] + best[2]) / 2

    if split_x is None:
        return [payload for _, payload in sorted(items, key=lambda it: (it[0][1], it[0][0]))]

    ordered: list[object] = []
    left: list[tuple[tuple[float, float, float, float], object]] = []
    right: list[tuple[tuple[float, float, float, float], object]] = []

    def flush() -> None:
        left.sort(key=lambda it: it[0][1])
        right.sort(key=lambda it: it[0][1])
        ordered.extend(payload for _, payload in left)
        ordered.extend(payload for _, payload in right)
        left.clear()
        right.clear()

    for bbox, payload in sorted(items, key=lambda it: it[0][1]):
        if (bbox[2] - bbox[0]) > narrow_threshold:
            flush()
            ordered.append(payload)
        else:
            (left if bbox[0] < split_x else right).append((bbox, payload))
    flush()
    return ordered


def _body_font_size(sizes: list[float]) -> float:
    if not sizes:
        return 11.0
    counts: dict[float, int] = {}
    for size in sizes:
        counts[size] = counts.get(size, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _heading_level(size: float, body_size: float, distinct_larger: list[float]) -> int:
    """`distinct_larger` is computed from a *sample* of pages (analyze_document
    only scans up to `sample_pages` of them for font-size stats), so a
    heading size seen only on an unsampled page may not be an exact
    match in that list - `.index()` would raise ValueError. Bucket by
    "at least this large" instead of requiring equality."""
    if not distinct_larger:
        return 1
    for rank, candidate in enumerate(sorted(distinct_larger, reverse=True)):
        if size >= candidate:
            return min(rank + 1, 3)
    return min(len(distinct_larger) + 1, 3)


def _detect_furniture(layouts: list, body_size: float) -> tuple[set[str], set[tuple[str, int]]]:
    """Detect running headers/footers from a page sample (section 2, 6):
    small text (never heading-sized - a real title is never mistaken for
    furniture) sitting in the outer 8% of the page that either repeats
    verbatim across most sampled pages (an author name, a running
    title) or is a lone number recurring in the same corner (a page
    number - the digits differ per page, so it's matched by *position*,
    not by exact text). Needs at least 3 sampled pages to tell "repeated
    boilerplate" apart from "this page happens to have a short line up
    there" - never runs on a short document.
    """
    if len(layouts) < 3:
        return set(), set()

    text_counts: dict[str, int] = {}
    position_counts: dict[tuple[str, int], int] = {}
    numberish_texts: set[str] = set()

    for layout in layouts:
        height, width = layout.height or 1.0, layout.width or 1.0
        for block in layout.blocks:
            text = block.text.strip()
            if not text or len(text) > 60 or block.max_size > body_size * 0.95:
                continue
            y0, y1 = block.bbox[1], block.bbox[3]
            in_top, in_bottom = y0 < height * 0.08, y1 > height * 0.92
            if not (in_top or in_bottom):
                continue
            text_counts[text] = text_counts.get(text, 0) + 1
            if _PAGE_NUMBER_RE.match(text):
                zone = "top" if in_top else "bottom"
                h_bucket = int((block.bbox[0] + block.bbox[2]) / 2 / width * 3)
                position_counts[(zone, h_bucket)] = position_counts.get((zone, h_bucket), 0) + 1
                numberish_texts.add(text)

    threshold = max(2, round(len(layouts) * 0.5))
    furniture_texts = {text for text, count in text_counts.items() if count >= threshold}
    numeric_zones = {zone for zone, count in position_counts.items() if count >= threshold}
    return furniture_texts, numeric_zones


def _is_furniture(
    block: TextBlock,
    layout,
    furniture_texts: set[str],
    numeric_zones: set[tuple[str, int]],
    body_size: float,
) -> bool:
    text = block.text.strip()
    if text in furniture_texts:
        return True
    if numeric_zones and _PAGE_NUMBER_RE.match(text) and block.max_size <= body_size * 0.95:
        height, width = layout.height or 1.0, layout.width or 1.0
        y0, y1 = block.bbox[1], block.bbox[3]
        in_top, in_bottom = y0 < height * 0.08, y1 > height * 0.92
        if in_top or in_bottom:
            zone = "top" if in_top else "bottom"
            h_bucket = int((block.bbox[0] + block.bbox[2]) / 2 / width * 3)
            if (zone, h_bucket) in numeric_zones:
                return True
    return False


def _is_table_overlap(bbox: tuple[float, float, float, float], tables: list[TableData]) -> bool:
    bx0, by0, bx1, by1 = bbox
    for table in tables:
        tx0, ty0, tx1, ty1 = table.bbox
        ix0, iy0 = max(bx0, tx0), max(by0, ty0)
        ix1, iy1 = min(bx1, tx1), min(by1, ty1)
        if ix1 > ix0 and iy1 > iy0:
            area = (ix1 - ix0) * (iy1 - iy0)
            block_area = max((bx1 - bx0) * (by1 - by0), 1.0)
            if area / block_area > 0.5:
                return True
    return False


def _find_link_for_span(bbox: tuple[float, float, float, float], links: list[LinkData]) -> Optional[str]:
    bx0, by0, bx1, by1 = bbox
    span_area = max((bx1 - bx0) * (by1 - by0), 1.0)
    best_uri: Optional[str] = None
    best_ratio = 0.0
    for link in links:
        lx0, ly0, lx1, ly1 = link.bbox
        ix0, iy0 = max(bx0, lx0), max(by0, ly0)
        ix1, iy1 = min(bx1, lx1), min(by1, ly1)
        if ix1 > ix0 and iy1 > iy0:
            ratio = ((ix1 - ix0) * (iy1 - iy0)) / span_area
            if ratio > best_ratio:
                best_ratio, best_uri = ratio, link.uri
    return best_uri if best_ratio > 0.4 else None


def _wrap_emphasis(text: str, bold: bool, italic: bool) -> str:
    """Wrap only the non-whitespace core of `text` in **/*, so a span's
    own leading/trailing spacing (word separation between spans) never
    ends up *inside* the emphasis markers - "** word**" doesn't render
    as bold in CommonMark, "**word**" does."""
    if not (bold or italic):
        return text
    core = text.strip(" ")
    if not core:
        return text
    lead = text[: len(text) - len(text.lstrip(" "))]
    trail = text[len(text.rstrip(" ")) :]
    if italic:
        core = f"*{core}*"
    if bold:
        core = f"**{core}**"
    return lead + core + trail


def _render_spans(
    spans: list[TextSpan],
    links: Optional[list[LinkData]],
    baseline_bold: bool,
    baseline_italic: bool,
    skip_chars: int = 0,
) -> str:
    """Render spans as Markdown text: real bold/italic emphasis and real
    hyperlinks preserved from the PDF, never invented (section 6). Bold
    is only rendered when it's *not* the document's own baseline style -
    a body font that happens to be bold everywhere carries no emphasis
    signal, so treating it as such would wrap every sentence in ** for
    no informational gain (section 33: sober, not noisy).

    `skip_chars` drops the first N raw characters (a detected bullet/
    number marker) before formatting starts, so marker-stripping and
    emphasis rendering never have to operate on the same string.

    Consecutive spans that share the same bold/italic/link state are
    merged into a single emphasis run before wrapping: a "Label:" span
    immediately followed by a " rest of sentence" span in the same bold
    run is extremely common (PDF text is split into spans wherever the
    source document changed anything, even when the *style* didn't
    change across that split), and wrapping each individually would
    produce "**Label:** **rest**" - visually harmless but needlessly
    noisy - or worse, adjacent runs with different bold/italic combos
    landing several `*` deep into each other.
    """
    entries: list[tuple[str, bool, bool, Optional[str]]] = []
    remaining_skip = skip_chars
    for span in spans:
        text = span.text
        if remaining_skip > 0:
            if remaining_skip >= len(text):
                remaining_skip -= len(text)
                continue
            text = text[remaining_skip:]
            remaining_skip = 0
        if not text:
            continue
        uri = _find_link_for_span(span.bbox, links) if links else None
        entries.append((text, span.bold and not baseline_bold, span.italic and not baseline_italic, uri))

    merged: list[tuple[str, bool, bool, Optional[str]]] = []
    for text, bold, italic, uri in entries:
        if merged and merged[-1][1:] == (bold, italic, uri):
            merged[-1] = (merged[-1][0] + text, bold, italic, uri)
        else:
            merged.append((text, bold, italic, uri))

    parts: list[str] = []
    for text, bold, italic, uri in merged:
        rendered = _wrap_emphasis(text, bold, italic)
        if uri:
            rendered = f"[{rendered}]({uri})"
        parts.append(rendered)
    return "".join(parts)


def _render_block_text(
    block: TextBlock,
    links: Optional[list[LinkData]],
    baseline_bold: bool,
    baseline_italic: bool,
    skip_chars: int = 0,
) -> str:
    lines_rendered = []
    remaining_skip = skip_chars
    for line in block.lines:
        skip_here = min(remaining_skip, len(line.text))
        lines_rendered.append(_render_spans(line.spans, links, baseline_bold, baseline_italic, skip_here))
        remaining_skip = max(0, remaining_skip - len(line.text))
    return "\n".join(lines_rendered)


def _classify_text_block(
    block: TextBlock,
    body_size: float,
    heading_sizes: list[float],
    page_links: Optional[list[LinkData]] = None,
    baseline_bold: bool = False,
    baseline_italic: bool = False,
) -> list[DocBlock]:
    """Returns a *list* because a PDF text extractor commonly merges
    several consecutive list items that sit close together into one
    physical block (section 9): if 72pt/"start of line at 90pt" both
    look like list markers, this splits per-line instead of treating
    the whole merged block as a single list item with a literal
    "- second bullet" stuck inside its text.
    """
    text = block.text.strip()
    first_line = block.lines[0] if block.lines else None
    is_monospace = bool(first_line) and any(
        hint in (s.font or "").lower() for s in first_line.spans for hint in _MONOSPACE_HINTS
    )

    if is_monospace and len(block.lines) >= 1:
        return [DocBlock(kind="code", page_index=0, bbox=block.bbox, text=block.text)]

    if block.max_size > body_size * 1.15 and len(text) < 200 and "\n" not in text.strip():
        level = _heading_level(block.max_size, body_size, heading_sizes)
        # Headings are bold almost by design (large font already marks
        # them as a heading) - wrapping "### **Title**" in emphasis too
        # is redundant, so bold/italic is suppressed here specifically
        # (passing baseline=True disables the wrap unconditionally)
        # while link rendering still applies normally.
        rendered = _render_block_text(block, page_links, baseline_bold=True, baseline_italic=True).strip()
        return [DocBlock(kind="heading", page_index=0, bbox=block.bbox, text=rendered, level=level)]

    line_texts = [line.text for line in block.lines]
    is_bullet_line = [bool(_BULLET_RE.match(t)) for t in line_texts]
    is_numbered_line = [bool(_NUMBERED_RE.match(t)) and len(t) < 500 for t in line_texts]

    if any(is_bullet_line) or any(is_numbered_line):
        results: list[DocBlock] = []
        for line, line_text, is_bullet, is_numbered in zip(block.lines, line_texts, is_bullet_line, is_numbered_line):
            if not line_text.strip():
                continue
            if is_bullet:
                skip = _BULLET_RE.match(line_text).end()
                rendered = _render_spans(line.spans, page_links, baseline_bold, baseline_italic, skip).strip()
                results.append(DocBlock(kind="list_item", page_index=0, bbox=block.bbox, text=rendered, ordered=False))
            elif is_numbered:
                skip = _NUMBERED_RE.match(line_text).end()
                rendered = _render_spans(line.spans, page_links, baseline_bold, baseline_italic, skip).strip()
                results.append(DocBlock(kind="list_item", page_index=0, bbox=block.bbox, text=rendered, ordered=True))
            else:
                rendered = _render_spans(line.spans, page_links, baseline_bold, baseline_italic).strip()
                results.append(DocBlock(kind="paragraph", page_index=0, bbox=block.bbox, text=rendered))
        return results

    is_italic = bool(first_line) and all(s.italic for s in first_line.spans if s.text.strip())
    if is_italic:
        # Confirmed/downgraded by the caller, which knows this page's left
        # margin - italics alone doesn't mean "quote", indentation does.
        rendered = _render_block_text(block, page_links, baseline_bold, baseline_italic).strip()
        return [DocBlock(kind="quote", page_index=0, bbox=block.bbox, text=rendered)]

    rendered = _render_block_text(block, page_links, baseline_bold, baseline_italic).strip()
    return [DocBlock(kind="paragraph", page_index=0, bbox=block.bbox, text=rendered)]


def analyze_document(
    pdf: PDFDocument,
    extract_images: bool = True,
    extract_links: bool = True,
    sample_pages: int = 40,
    ocr_page_text: Optional[Callable[[int], Optional[str]]] = None,
    on_page: Optional[Callable[[int, int], None]] = None,
    min_image_dim: int = 60,
    detect_headings: bool = True,
    preserve_lists: bool = True,
    detect_tables: bool = True,
) -> Iterator[DocBlock]:
    """Walk every page of `pdf`, yielding DocBlock in natural reading
    order, already classified into headings/lists/tables/images/quotes/
    code/paragraphs. A generator rather than a list (section 5, 51): for
    a document with thousands of pages/images, the caller (markdown_builder)
    consumes and writes out each block - including image bytes - before
    asking for the next one, so peak memory stays around one page's
    worth of content instead of the whole document's.

    `ocr_page_text`, if given, is called for any page with no
    extractable text layer at all (a scanned page); its return value
    becomes plain paragraph blocks - OCR text never gets heading/list/
    table classification, since Tesseract gives us words, not layout
    metadata to classify structure from.

    `on_page(page_index, page_count)` is called after every page, so a
    caller can report progress and raise to cooperatively cancel a very
    large document mid-analysis.
    """
    page_count = pdf.page_count
    sample_indices = list(range(0, page_count, max(1, page_count // sample_pages)))[:sample_pages]

    all_sizes: list[float] = []
    sampled_layouts = []
    bold_spans = italic_spans = total_spans = 0
    for i in sample_indices:
        layout = pdf.get_page_layout(i)
        sampled_layouts.append(layout)
        for block in layout.blocks:
            for line in block.lines:
                for s in line.spans:
                    if not s.text.strip():
                        continue
                    all_sizes.append(s.size)
                    total_spans += 1
                    bold_spans += s.bold
                    italic_spans += s.italic
    body_size = _body_font_size(all_sizes)
    heading_sizes = sorted({s for s in all_sizes if s > body_size * 1.15}, reverse=True)[:3]
    # If most of the document's own body text is already bold/italic,
    # that's the baseline style, not an emphasis signal (section 33).
    baseline_bold = total_spans > 0 and (bold_spans / total_spans) > 0.7
    baseline_italic = total_spans > 0 and (italic_spans / total_spans) > 0.7
    furniture_texts, numeric_zones = _detect_furniture(sampled_layouts, body_size)

    for page_index in range(page_count):
        layout = pdf.get_page_layout(page_index)

        if layout.char_count == 0 and ocr_page_text is not None:
            recognized = ocr_page_text(page_index)
            if recognized and recognized.strip():
                for paragraph in re.split(r"\n\s*\n", recognized.strip()):
                    if paragraph.strip():
                        yield DocBlock(
                            kind="paragraph",
                            page_index=page_index,
                            bbox=(0.0, 0.0, layout.width, layout.height),
                            text=paragraph.strip(),
                            ocr_source=True,
                        )
            if on_page:
                on_page(page_index, page_count)
            continue

        left_margin = min((b.bbox[0] for b in layout.blocks), default=0.0)

        items: list[tuple[tuple[float, float, float, float], object]] = []

        for block in layout.blocks:
            if not block.text.strip():
                continue
            if _is_furniture(block, layout, furniture_texts, numeric_zones, body_size):
                continue
            if detect_tables and _is_table_overlap(block.bbox, layout.tables):
                continue
            links = layout.links if extract_links else None
            for doc_block in _classify_text_block(block, body_size, heading_sizes, links, baseline_bold, baseline_italic):
                if doc_block.kind == "quote" and block.bbox[0] <= left_margin + 8:
                    doc_block.kind = "paragraph"  # not actually indented relative to this page
                if not detect_headings and doc_block.kind == "heading":
                    doc_block.kind = "paragraph"
                if not preserve_lists and doc_block.kind == "list_item":
                    doc_block.kind = "paragraph"
                doc_block.page_index = page_index
                items.append((block.bbox, doc_block))

        if detect_tables:
            for table in layout.tables:
                doc_block = DocBlock(kind="table", page_index=page_index, bbox=table.bbox, rows=table.rows)
                items.append((table.bbox, doc_block))

        if extract_images:
            for image in pdf.extract_page_images(page_index, min_dim=min_image_dim):
                bbox = image.bbox or (0.0, 0.0, layout.width, 1.0)
                doc_block = DocBlock(kind="image", page_index=page_index, bbox=bbox, image=image)
                items.append((bbox, doc_block))

        yield from _reading_order(items, layout.width)
        if on_page:
            on_page(page_index, page_count)
