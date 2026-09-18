"""Renders a list of DocBlock (structure.py) into Markdown text plus an
assets/ folder (section 6-10). Rendering never invents content: a block
that couldn't be classified confidently still renders as a paragraph
with its real extracted text, never as a placeholder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .structure import DocBlock

_LEADING_MD_RE = re.compile(r"^(\s*)([#>*+-]|\d+[.)])(\s|$)")

AssetWriter = Callable[[bytes, str], str]  # (data, ext) -> relative asset path, e.g. "assets/image-001.png"


@dataclass
class MarkdownStats:
    """Counts gathered while rendering, for ConversionMetadata (section
    15) - computed in the same pass instead of a second one, so a
    generator of blocks only ever has to be consumed once."""

    images_written: int = 0
    tables_rendered: int = 0
    headings: int = 0
    ocr_pages: set[int] = field(default_factory=set)
    pages_seen: set[int] = field(default_factory=set)
    garbled_chars: int = 0


def _escape_inline(text: str) -> str:
    """Escape only what would otherwise be parsed as Markdown block
    syntax (leading #, -, *, digit-dot) so text lifted verbatim from the
    PDF can't accidentally turn into a heading/list/blockquote it never
    was. Deliberately does not escape every '.', '(', '_' etc. inside a
    sentence - that would make ordinary prose unreadable for no benefit.
    """
    text = text.replace("\\", "\\\\")
    lines = []
    for line in text.split("\n"):
        match = _LEADING_MD_RE.match(line)
        if match:
            line = line[: match.start(2)] + "\\" + line[match.start(2) :]
        lines.append(line)
    return "\n".join(lines)


def _render_table(rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    if len(rows) < 2:
        # Not enough rows to justify inventing a header separator; keep
        # the original alignment literally instead of faking table syntax.
        return ["```", *("\t".join(cell for cell in row) for row in rows), "```"]

    width = max(len(row) for row in rows)

    def pad(row: list[str]) -> list[str]:
        return row + [""] * (width - len(row))

    def esc(cell: str) -> str:
        return (cell or "").replace("|", "\\|").replace("\n", " ").strip()

    header = pad(rows[0])
    lines = [
        "| " + " | ".join(esc(c) for c in header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in rows[1:]:
        lines.append("| " + " | ".join(esc(c) for c in pad(row)) + " |")
    return lines


def build_markdown(
    blocks: Iterable[DocBlock],
    write_asset: AssetWriter,
    extract_images: bool = True,
    preserve_page_references: bool = True,
) -> tuple[str, MarkdownStats]:
    lines: list[str] = []
    stats = MarkdownStats()
    current_page: int | None = None
    open_list_ordered: bool | None = None

    def close_list() -> None:
        nonlocal open_list_ordered
        open_list_ordered = None

    for block in blocks:
        stats.pages_seen.add(block.page_index)
        if block.ocr_source:
            stats.ocr_pages.add(block.page_index)
        if block.text:
            # PyMuPDF/the PDF's own embedded font is what decodes glyphs to
            # text; a font with a missing/broken ToUnicode CMap makes some
            # characters undecodable (surfaced as U+FFFD) - this is a
            # property of the source file, not something the extraction
            # step chose to guess wrong, so it's counted rather than
            # "fixed" with a guess of our own (section 2: never invent).
            stats.garbled_chars += block.text.count("�")

        if preserve_page_references and block.page_index != current_page:
            current_page = block.page_index
            close_list()
            lines.append("")
            lines.append(f"<!-- page {current_page + 1} -->")

        if block.kind == "heading":
            close_list()
            stats.headings += 1
            lines.append("")
            lines.append(f"{'#' * min(max(block.level, 1), 6)} {_escape_inline(block.text)}")

        elif block.kind == "paragraph":
            close_list()
            if block.text.strip():
                lines.append("")
                lines.append(_escape_inline(block.text))

        elif block.kind == "list_item":
            if open_list_ordered != block.ordered:
                lines.append("")
                open_list_ordered = block.ordered
            marker = "1." if block.ordered else "-"
            lines.append(f"{marker} {_escape_inline(block.text)}")

        elif block.kind == "quote":
            close_list()
            lines.append("")
            for text_line in block.text.splitlines() or [block.text]:
                lines.append(f"> {text_line}")

        elif block.kind == "code":
            close_list()
            lines.append("")
            lines.append("```")
            lines.extend(block.text.splitlines())
            lines.append("```")

        elif block.kind == "table":
            close_list()
            stats.tables_rendered += 1
            lines.append("")
            lines.extend(_render_table(block.rows or []))

        elif block.kind == "image" and extract_images and block.image:
            close_list()
            asset_path = write_asset(block.image.data, block.image.ext)
            stats.images_written += 1
            lines.append("")
            lines.append(f"![Figure]({asset_path})")

    text = "\n".join(lines).strip()
    return ((text + "\n") if text else ""), stats


def build_text(blocks: Iterable[DocBlock]) -> str:
    """Plain-text rendering of the same blocks: no Markdown syntax, no
    images (nothing meaningful to show inline), tables rendered as
    simple aligned rows."""
    lines: list[str] = []
    for block in blocks:
        if block.kind == "heading":
            lines.append("")
            lines.append(block.text.upper() if block.level == 1 else block.text)
        elif block.kind in ("paragraph", "quote", "code"):
            if block.text.strip():
                lines.append("")
                lines.append(block.text)
        elif block.kind == "list_item":
            lines.append(f"- {block.text}")
        elif block.kind == "table":
            for row in block.rows or []:
                lines.append("\t".join(row))
            lines.append("")
    text = "\n".join(lines).strip()
    return (text + "\n") if text else ""
