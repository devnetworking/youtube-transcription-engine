from src.documents.markdown_builder import build_markdown, build_text
from src.documents.structure import DocBlock


def _asset_writer(data: bytes, ext: str) -> str:
    return f"assets/image-{ext}"


def test_build_markdown_renders_heading_and_paragraph():
    blocks = [
        DocBlock(kind="heading", page_index=0, bbox=(0, 0, 0, 0), text="Title", level=1),
        DocBlock(kind="paragraph", page_index=0, bbox=(0, 0, 0, 0), text="Some text."),
    ]
    text, stats = build_markdown(blocks, _asset_writer, preserve_page_references=False)
    assert "# Title" in text
    assert "Some text." in text
    assert stats.headings == 1


def test_build_markdown_never_invents_missing_header_row():
    # A single-row "table" isn't enough to justify a Markdown header
    # separator that wasn't in the source - it should render literally.
    blocks = [DocBlock(kind="table", page_index=0, bbox=(0, 0, 0, 0), rows=[["only", "row"]])]
    text, stats = build_markdown(blocks, _asset_writer, preserve_page_references=False)
    assert "|---|" not in text.replace(" ", "")
    assert "only" in text and "row" in text


def test_build_markdown_renders_proper_pipe_table():
    blocks = [DocBlock(
        kind="table", page_index=0, bbox=(0, 0, 0, 0),
        rows=[["Name", "Score"], ["Alice", "90"], ["Bob", "85"]],
    )]
    text, stats = build_markdown(blocks, _asset_writer, preserve_page_references=False)
    assert "| Name | Score |" in text
    assert "| --- | --- |" in text
    assert "| Alice | 90 |" in text
    assert stats.tables_rendered == 1


def test_build_markdown_escapes_leading_markdown_syntax_in_body_text():
    blocks = [DocBlock(kind="paragraph", page_index=0, bbox=(0, 0, 0, 0), text="# Not actually a heading")]
    text, _ = build_markdown(blocks, _asset_writer, preserve_page_references=False)
    assert text.strip().startswith("\\#")


def test_build_markdown_writes_image_asset_and_counts_it():
    from src.documents.pdf_engine import ImageData
    blocks = [DocBlock(kind="image", page_index=0, bbox=(0, 0, 0, 0), image=ImageData(data=b"fake", ext="png", bbox=None))]
    text, stats = build_markdown(blocks, _asset_writer, extract_images=True, preserve_page_references=False)
    assert "![Figure](assets/image-png)" in text
    assert stats.images_written == 1


def test_build_markdown_skips_images_when_disabled():
    from src.documents.pdf_engine import ImageData
    blocks = [DocBlock(kind="image", page_index=0, bbox=(0, 0, 0, 0), image=ImageData(data=b"fake", ext="png", bbox=None))]
    text, stats = build_markdown(blocks, _asset_writer, extract_images=False, preserve_page_references=False)
    assert "![Figure]" not in text
    assert stats.images_written == 0


def test_build_markdown_groups_ordered_and_unordered_lists_separately():
    blocks = [
        DocBlock(kind="list_item", page_index=0, bbox=(0, 0, 0, 0), text="a", ordered=False),
        DocBlock(kind="list_item", page_index=0, bbox=(0, 0, 0, 0), text="b", ordered=False),
    ]
    text, _ = build_markdown(blocks, _asset_writer, preserve_page_references=False)
    assert text.count("- a") == 1
    assert text.count("- b") == 1


def test_build_markdown_counts_undecodable_characters():
    # A font with a broken/missing ToUnicode CMap makes PyMuPDF emit
    # U+FFFD for glyphs it can't map to text - counted so a conversion
    # can warn about it, never silently guessed at.
    blocks = [DocBlock(kind="paragraph", page_index=0, bbox=(0, 0, 0, 0), text="M�thodes et �valuation")]
    _, stats = build_markdown(blocks, _asset_writer, preserve_page_references=False)
    assert stats.garbled_chars == 2


def test_build_text_has_no_markdown_syntax():
    blocks = [
        DocBlock(kind="heading", page_index=0, bbox=(0, 0, 0, 0), text="Title", level=1),
        DocBlock(kind="list_item", page_index=0, bbox=(0, 0, 0, 0), text="item one", ordered=False),
    ]
    text = build_text(blocks)
    assert "#" not in text
    assert "TITLE" in text
    assert "item one" in text
