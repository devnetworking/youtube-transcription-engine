import pymupdf as fitz

from src.documents.pdf_engine import TextSpan, open_pdf
from src.documents.structure import _heading_level, _render_spans, _wrap_emphasis, analyze_document


def _span(text: str, bold: bool = False, italic: bool = False) -> TextSpan:
    return TextSpan(text=text, size=11.0, bold=bold, italic=italic, font="Test", bbox=(0.0, 0.0, 10.0, 10.0))


def test_wrap_emphasis_bold():
    assert _wrap_emphasis("hello", bold=True, italic=False) == "**hello**"


def test_wrap_emphasis_preserves_surrounding_spaces():
    # "** word**" is not valid emphasis in CommonMark - the markers must
    # hug the non-whitespace content, so spacing has to stay outside them.
    assert _wrap_emphasis(" hello ", bold=True, italic=False) == " **hello** "


def test_wrap_emphasis_bold_and_italic_combine():
    assert _wrap_emphasis("hello", bold=True, italic=True) == "***hello***"


def test_wrap_emphasis_noop_without_formatting():
    assert _wrap_emphasis("hello", False, False) == "hello"


def test_wrap_emphasis_all_whitespace_is_untouched():
    assert _wrap_emphasis("   ", True, False) == "   "


def test_render_spans_wraps_bold_span_when_not_the_document_baseline():
    spans = [_span("Label: "), _span("bold part", bold=True), _span(" rest")]
    assert _render_spans(spans, None, baseline_bold=False, baseline_italic=False) == "Label: **bold part** rest"


def test_render_spans_ignores_bold_when_it_is_the_baseline_style():
    # A body font that's bold everywhere carries no emphasis signal -
    # section 33: wrapping every sentence in ** would just be noise.
    spans = [_span("all bold text")]
    for s in spans:
        s.bold = True
    assert _render_spans(spans, None, baseline_bold=True, baseline_italic=False) == "all bold text"


def test_render_spans_merges_adjacent_spans_with_identical_formatting():
    # "Label:" and " rest" are two separate spans (common in real PDFs)
    # but share the same bold state - they should render as one
    # continuous "**Label: rest**", not "**Label:** ** rest**".
    spans = [_span("Bonne nouvelle:", bold=True), _span(" tout va bien", bold=True)]
    result = _render_spans(spans, None, baseline_bold=False, baseline_italic=False)
    assert result == "**Bonne nouvelle: tout va bien**"
    assert result.count("**") == 2


def test_render_spans_does_not_merge_spans_with_different_formatting():
    spans = [_span("plain "), _span("bold", bold=True)]
    result = _render_spans(spans, None, baseline_bold=False, baseline_italic=False)
    assert result == "plain **bold**"


def test_render_spans_skip_chars_strips_marker_before_formatting():
    spans = [_span("(1) "), _span("First item", bold=True)]
    result = _render_spans(spans, None, baseline_bold=False, baseline_italic=False, skip_chars=4)
    assert result == "**First item**"


def test_heading_level_handles_size_not_in_sampled_list():
    # `distinct_larger` comes from a *sample* of pages; a real document's
    # heading on an unsampled page can have a font size that isn't an
    # exact match in that list (regression: this used to raise
    # `ValueError: 16.0 is not in list` via `list.index()`).
    assert _heading_level(16.0, body_size=11.0, distinct_larger=[24.0, 18.0, 14.0]) == 3


def test_heading_level_handles_size_larger_than_any_sampled():
    assert _heading_level(30.0, body_size=11.0, distinct_larger=[24.0, 18.0]) == 1


def test_heading_level_handles_size_smaller_than_all_sampled():
    assert _heading_level(12.5, body_size=11.0, distinct_larger=[24.0, 18.0, 14.0]) == 3


def test_heading_level_exact_match_still_works():
    assert _heading_level(24.0, body_size=11.0, distinct_larger=[24.0, 18.0, 14.0]) == 1
    assert _heading_level(18.0, body_size=11.0, distinct_larger=[24.0, 18.0, 14.0]) == 2


def test_analyze_document_detects_heading_and_paragraph(make_pdf):
    path = make_pdf(
        pages=1,
        heading="Chapter One",
        body="This is a body paragraph with normal sized text that should not be a heading.",
    )
    with open_pdf(path) as pdf:
        blocks = list(analyze_document(pdf))
    kinds = [b.kind for b in blocks]
    assert "heading" in kinds
    assert "paragraph" in kinds
    heading = next(b for b in blocks if b.kind == "heading")
    assert "Chapter One" in heading.text


def test_analyze_document_splits_merged_bullet_list(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "- First item", fontsize=11)
    page.insert_text((72, 86), "- Second item", fontsize=11)
    page.insert_text((72, 100), "- Third item", fontsize=11)
    path = tmp_path / "list.pdf"
    doc.save(str(path))
    doc.close()

    with open_pdf(path) as pdf:
        blocks = list(analyze_document(pdf))
    list_items = [b for b in blocks if b.kind == "list_item"]
    assert len(list_items) == 3
    assert [b.text for b in list_items] == ["First item", "Second item", "Third item"]
    assert all(not b.ordered for b in list_items)


def test_analyze_document_detects_numbered_list(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "1. Alpha", fontsize=11)
    page.insert_text((72, 86), "2. Beta", fontsize=11)
    path = tmp_path / "numbered.pdf"
    doc.save(str(path))
    doc.close()

    with open_pdf(path) as pdf:
        blocks = list(analyze_document(pdf))
    list_items = [b for b in blocks if b.kind == "list_item"]
    assert len(list_items) == 2
    assert all(b.ordered for b in list_items)


def test_analyze_document_recovers_two_column_reading_order(tmp_path):
    doc = fitz.open()
    page = doc.new_page()  # default letter size, width ~612pt
    # Left column, top to bottom.
    page.insert_text((60, 100), "Left top", fontsize=11)
    page.insert_text((60, 400), "Left bottom", fontsize=11)
    # Right column, top to bottom.
    page.insert_text((330, 100), "Right top", fontsize=11)
    page.insert_text((330, 400), "Right bottom", fontsize=11)
    path = tmp_path / "columns.pdf"
    doc.save(str(path))
    doc.close()

    with open_pdf(path) as pdf:
        blocks = [b for b in analyze_document(pdf) if b.kind == "paragraph"]
    texts = [b.text for b in blocks]
    # Natural reading order: whole left column, then whole right column -
    # never left-top, right-top, left-bottom, right-bottom (interleaved).
    assert texts.index("Left top") < texts.index("Left bottom") < texts.index("Right top")


def test_analyze_document_uses_ocr_fallback_for_scanned_page(blank_pdf):
    def fake_ocr(page_index):
        return "Recognized text from OCR."

    with open_pdf(blank_pdf) as pdf:
        blocks = list(analyze_document(pdf, ocr_page_text=fake_ocr))
    assert len(blocks) == 1
    assert blocks[0].ocr_source is True
    assert blocks[0].text == "Recognized text from OCR."


def test_analyze_document_respects_detect_headings_false(make_pdf):
    path = make_pdf(pages=1, heading="Chapter One", body="Body text.")
    with open_pdf(path) as pdf:
        blocks = list(analyze_document(pdf, detect_headings=False))
    assert all(b.kind != "heading" for b in blocks)


def test_analyze_document_detects_parenthesized_numbered_list(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "(1) First item", fontsize=11)
    page.insert_text((72, 90), "(2) Second item", fontsize=11)
    path = tmp_path / "paren_list.pdf"
    doc.save(str(path))
    doc.close()

    with open_pdf(path) as pdf:
        blocks = list(analyze_document(pdf))
    list_items = [b for b in blocks if b.kind == "list_item"]
    assert [b.text for b in list_items] == ["First item", "Second item"]
    assert all(b.ordered for b in list_items)


def test_analyze_document_removes_repeated_footer_text(tmp_path):
    doc = fitz.open()
    for i in range(4):
        page = doc.new_page()
        page.insert_text((72, 100), f"Real content on page {i + 1}.", fontsize=11)
        page.insert_text((72, page.rect.height - 30), "Confidential - Author Name", fontsize=8)
    path = tmp_path / "footer.pdf"
    doc.save(str(path))
    doc.close()

    with open_pdf(path) as pdf:
        blocks = list(analyze_document(pdf))
    texts = [b.text for b in blocks]
    assert not any("Confidential" in t for t in texts)
    assert sum("Real content on page" in t for t in texts) == 4


def test_analyze_document_removes_repeated_page_numbers(tmp_path):
    doc = fitz.open()
    for i in range(4):
        page = doc.new_page()
        page.insert_text((72, 100), f"Body text {i + 1}.", fontsize=11)
        page.insert_text((page.rect.width - 40, page.rect.height - 30), str(i + 1), fontsize=9)
    path = tmp_path / "pagenum.pdf"
    doc.save(str(path))
    doc.close()

    with open_pdf(path) as pdf:
        blocks = list(analyze_document(pdf))
    texts = [b.text.strip() for b in blocks]
    assert not any(t in ("1", "2", "3", "4") for t in texts)
    assert sum(t.startswith("Body text") for t in texts) == 4


def test_analyze_document_keeps_distinct_large_headings_near_top(tmp_path):
    # Furniture detection must never eat a real per-page heading just
    # because it happens to sit near the top of the page - only text
    # that's both small *and* repeated/positional is furniture.
    doc = fitz.open()
    for i in range(4):
        page = doc.new_page()
        page.insert_text((72, 40), f"Chapter {i + 1}", fontsize=28, fontname="hebo")
        page.insert_text((72, 120), "Body paragraph text here for realism and length.", fontsize=11)
        page.insert_text((72, 138), "A second body line to keep body size the mode.", fontsize=11)
    path = tmp_path / "headings.pdf"
    doc.save(str(path))
    doc.close()

    with open_pdf(path) as pdf:
        blocks = list(analyze_document(pdf))
    headings = [b.text for b in blocks if b.kind == "heading"]
    assert headings == ["Chapter 1", "Chapter 2", "Chapter 3", "Chapter 4"]
