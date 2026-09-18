import pytest

from src.documents.exceptions import CorruptPDFError
from src.documents.pdf_engine import extract_pages, merge_pdfs, open_pdf


def test_open_pdf_reports_page_count(make_pdf):
    path = make_pdf(pages=3)
    with open_pdf(path) as pdf:
        assert pdf.page_count == 3


def test_open_pdf_rejects_corrupt_file(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a real pdf, just garbage bytes")
    with pytest.raises(CorruptPDFError):
        open_pdf(path)


def test_has_extractable_text_true_for_text_pdf(make_pdf):
    path = make_pdf(pages=1, body="Some real text content here.")
    with open_pdf(path) as pdf:
        assert pdf.has_extractable_text()


def test_has_extractable_text_false_for_blank_pdf(blank_pdf):
    with open_pdf(blank_pdf) as pdf:
        assert not pdf.has_extractable_text()


def test_render_thumbnail_produces_png_bytes(make_pdf):
    path = make_pdf(pages=1)
    with open_pdf(path) as pdf:
        data = pdf.render_thumbnail(0, max_dim=100)
    assert data.startswith(b"\x89PNG")


def test_merge_pdfs_combines_full_documents(make_pdf, tmp_path):
    a = make_pdf(pages=2, filename="a.pdf")
    b = make_pdf(pages=3, filename="b.pdf")
    out = tmp_path / "merged.pdf"
    count = merge_pdfs([(a, None), (b, None)], out)
    assert count == 5
    with open_pdf(out) as pdf:
        assert pdf.page_count == 5


def test_merge_pdfs_with_partial_page_selection(make_pdf, tmp_path):
    a = make_pdf(pages=5, filename="a.pdf")
    out = tmp_path / "merged.pdf"
    count = merge_pdfs([(a, [0, 2, 4])], out)
    assert count == 3


def test_merge_pdfs_preserves_input_order(make_pdf, tmp_path):
    a = make_pdf(pages=1, heading="Document A", filename="a.pdf")
    b = make_pdf(pages=1, heading="Document B", filename="b.pdf")
    out = tmp_path / "merged.pdf"
    merge_pdfs([(b, None), (a, None)], out)
    with open_pdf(out) as pdf:
        first_page_text = pdf.get_page_layout(0).blocks[0].text
    assert "Document B" in first_page_text


def test_extract_pages_writes_only_selected_pages(make_pdf, tmp_path):
    a = make_pdf(pages=5)
    out = tmp_path / "extracted.pdf"
    count = extract_pages(a, [1, 3], out)
    assert count == 2
    with open_pdf(out) as pdf:
        assert pdf.page_count == 2
