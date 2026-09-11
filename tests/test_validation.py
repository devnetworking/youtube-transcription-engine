from src.models import TranscriptSegment, VideoMetadata
from src.utils.validation import validate_output


def _metadata():
    return VideoMetadata(video_id="abc", url="https://www.youtube.com/watch?v=abc", title="A Video")


def test_validate_output_missing_files(tmp_path):
    issues = validate_output(tmp_path / "transcript.md", tmp_path / "transcript.txt", _metadata(), [])
    assert any("transcript.md was not created" in i for i in issues)
    assert any("transcript.txt was not created" in i for i in issues)


def test_validate_output_empty_files(tmp_path):
    md = tmp_path / "transcript.md"
    txt = tmp_path / "transcript.txt"
    md.write_text("", encoding="utf-8")
    txt.write_text("", encoding="utf-8")

    issues = validate_output(md, txt, _metadata(), [])
    assert any("empty" in i for i in issues)


def test_validate_output_passes_for_well_formed_files(tmp_path):
    md = tmp_path / "transcript.md"
    txt = tmp_path / "transcript.txt"
    md.write_text("# A Video\n\n## Video Information\n\ncontent", encoding="utf-8")
    txt.write_text("A Video\ncontent", encoding="utf-8")

    segments = [TranscriptSegment(start=0, end=1, text="hello")]
    issues = validate_output(md, txt, _metadata(), segments)
    assert issues == []


def test_validate_output_flags_out_of_order_timestamps(tmp_path):
    md = tmp_path / "transcript.md"
    txt = tmp_path / "transcript.txt"
    md.write_text("# A Video\n\n## Video Information\n\ncontent", encoding="utf-8")
    txt.write_text("A Video\ncontent", encoding="utf-8")

    segments = [
        TranscriptSegment(start=10, end=11, text="second"),
        TranscriptSegment(start=5, end=6, text="first"),
    ]
    issues = validate_output(md, txt, _metadata(), segments)
    assert any("not in order" in i for i in issues)


def test_validate_output_flags_markdown_table_in_txt(tmp_path):
    md = tmp_path / "transcript.md"
    txt = tmp_path / "transcript.txt"
    md.write_text("# A Video\n\n## Video Information\n\ncontent", encoding="utf-8")
    txt.write_text("| Term | Context |\n|---|---|\n", encoding="utf-8")

    segments = [TranscriptSegment(start=0, end=1, text="hello")]
    issues = validate_output(md, txt, _metadata(), segments)
    assert any("Markdown table" in i for i in issues)
