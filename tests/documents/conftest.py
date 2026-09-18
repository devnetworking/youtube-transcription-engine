"""Shared PDF-building fixture for documents module tests.

Builds tiny real PDFs with PyMuPDF instead of shipping binary fixture
files, so tests stay self-contained and never touch the network.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
import pytest


@pytest.fixture
def make_pdf(tmp_path: Path):
    counter = {"n": 0}

    def _factory(pages: int = 1, heading: str | None = None, body: str = "Body text.", filename: str | None = None) -> Path:
        doc = fitz.open()
        for i in range(pages):
            page = doc.new_page()
            y = 72
            if heading:
                page.insert_text((72, y), heading, fontsize=22, fontname="hebo")
                y += 40
            # Two separate body lines/spans, so body-sized text is the
            # font-size mode even when the heading text is a single span -
            # a real document's body text always outweighs its headings.
            page.insert_text((72, y), f"{body} (page {i + 1})", fontsize=11)
            page.insert_text((72, y + 16), "A second body line to keep the font-size distribution realistic.", fontsize=11)
        counter["n"] += 1
        path = tmp_path / (filename or f"test-{counter['n']}.pdf")
        doc.save(str(path))
        doc.close()
        return path

    return _factory


@pytest.fixture
def blank_pdf(tmp_path: Path) -> Path:
    """A PDF page with no text layer at all (simulates a scanned page)."""
    doc = fitz.open()
    doc.new_page()
    path = tmp_path / "blank.pdf"
    doc.save(str(path))
    doc.close()
    return path
