import json

from src.utils.filenames import sanitize_filename, unique_output_dir


def test_sanitize_filename_strips_invalid_chars():
    assert sanitize_filename('Weird: Title / With * Bad? Chars') == "Weird_Title_With_Bad_Chars"


def test_sanitize_filename_collapses_whitespace():
    assert sanitize_filename("Too   many    spaces") == "Too_many_spaces"


def test_sanitize_filename_empty_uses_fallback():
    assert sanitize_filename("", fallback="video_123") == "video_123"
    assert sanitize_filename(None, fallback="video_123") == "video_123"


def test_sanitize_filename_truncates_long_titles():
    long_title = "a" * 300
    result = sanitize_filename(long_title)
    assert len(result) <= 100


def test_sanitize_filename_reserved_windows_name():
    assert sanitize_filename("CON") == "_CON"


def test_unique_output_dir_new_directory(tmp_path):
    result = unique_output_dir(tmp_path, "My Video", "abc123")
    assert result == tmp_path / "My_Video"


def test_unique_output_dir_same_video_reuses_directory(tmp_path):
    existing = tmp_path / "My_Video"
    existing.mkdir()
    (existing / "metadata.json").write_text(json.dumps({"video_id": "abc123"}), encoding="utf-8")

    result = unique_output_dir(tmp_path, "My Video", "abc123")
    assert result == existing


def test_unique_output_dir_different_video_gets_suffixed(tmp_path):
    existing = tmp_path / "My_Video"
    existing.mkdir()
    (existing / "metadata.json").write_text(json.dumps({"video_id": "abc123"}), encoding="utf-8")

    result = unique_output_dir(tmp_path, "My Video", "xyz999")
    assert result == tmp_path / "My_Video_xyz999"
