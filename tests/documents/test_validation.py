import pytest

from src.documents.exceptions import InvalidUploadError, PageRangeError
from src.documents.validation import (
    format_page_ranges,
    parse_page_ranges,
    sanitize_display_name,
    validate_extension,
    validate_pdf_header,
)


def test_parse_single_page():
    assert parse_page_ranges("5", 10) == [5]


def test_parse_simple_range():
    assert parse_page_ranges("1-5", 10) == [1, 2, 3, 4, 5]


def test_parse_mixed_list_and_ranges():
    assert parse_page_ranges("1-5,8,10", 10) == [1, 2, 3, 4, 5, 8, 10]


def test_parse_dedupes_and_sorts():
    assert parse_page_ranges("5,1-3,2", 10) == [1, 2, 3, 5]


def test_parse_rejects_zero_page():
    with pytest.raises(PageRangeError):
        parse_page_ranges("0", 10)


def test_parse_rejects_malformed_token():
    with pytest.raises(PageRangeError):
        parse_page_ranges("-1", 10)


def test_parse_rejects_inverted_range():
    with pytest.raises(PageRangeError):
        parse_page_ranges("5-2", 10)


def test_parse_rejects_non_numeric():
    with pytest.raises(PageRangeError):
        parse_page_ranges("abc", 10)


def test_parse_rejects_empty_token_between_commas():
    with pytest.raises(PageRangeError):
        parse_page_ranges("3,,5", 10)


def test_parse_rejects_out_of_bounds_with_clear_message():
    with pytest.raises(PageRangeError) as exc_info:
        parse_page_ranges("74-90", 72)
    assert "72" in str(exc_info.value)


def test_parse_rejects_empty_spec():
    with pytest.raises(PageRangeError):
        parse_page_ranges("", 10)
    with pytest.raises(PageRangeError):
        parse_page_ranges("   ", 10)


def test_format_page_ranges_groups_consecutive_runs():
    assert format_page_ranges([1, 2, 3, 5, 7, 8]) == "1-3,5,7-8"


def test_format_page_ranges_empty():
    assert format_page_ranges([]) == ""


def test_sanitize_display_name_strips_path_separators():
    result = sanitize_display_name("evil/../../name.pdf")
    assert "/" not in result
    result = sanitize_display_name("evil\\..\\name.pdf")
    assert "\\" not in result


def test_sanitize_display_name_empty_uses_fallback():
    assert sanitize_display_name("") == "document.pdf"
    assert sanitize_display_name(None) == "document.pdf"


def test_sanitize_display_name_strips_control_characters():
    result = sanitize_display_name("evil\r\nname.pdf")
    assert "\r" not in result and "\n" not in result


def test_validate_pdf_header_accepts_real_pdf():
    validate_pdf_header(b"%PDF-1.7\n%more")


def test_validate_pdf_header_rejects_non_pdf():
    with pytest.raises(InvalidUploadError):
        validate_pdf_header(b"<html>not a pdf</html>")


def test_validate_extension_accepts_pdf():
    validate_extension("file.pdf", ["pdf"])


def test_validate_extension_rejects_other_types():
    with pytest.raises(InvalidUploadError):
        validate_extension("file.exe", ["pdf"])
