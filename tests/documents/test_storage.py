import hashlib
import io

import pytest

from src.documents.exceptions import PathSecurityError, ResourceLimitError
from src.documents.storage import UPLOADS, LocalStorageProvider


def test_save_stream_computes_checksum_and_size(tmp_path):
    storage = LocalStorageProvider(tmp_path)
    data = b"%PDF-1.4 hello world"
    key, size, checksum = storage.save_stream(UPLOADS, "doc1", "original.pdf", io.BytesIO(data))
    assert size == len(data)
    assert checksum == hashlib.sha256(data).hexdigest()
    assert storage.abs_path(key).read_bytes() == data


def test_save_stream_enforces_max_size_and_cleans_up(tmp_path):
    storage = LocalStorageProvider(tmp_path)
    data = b"x" * 1000
    with pytest.raises(ResourceLimitError):
        storage.save_stream(UPLOADS, "doc2", "original.pdf", io.BytesIO(data), max_size_bytes=10)
    assert not (tmp_path / UPLOADS / "doc2" / "original.pdf").exists()


def test_abs_path_blocks_path_traversal(tmp_path):
    storage = LocalStorageProvider(tmp_path)
    with pytest.raises(PathSecurityError):
        storage.abs_path("uploads/../../../etc/passwd")


def test_delete_entity_removes_directory(tmp_path):
    storage = LocalStorageProvider(tmp_path)
    key, _, _ = storage.save_stream(UPLOADS, "doc3", "original.pdf", io.BytesIO(b"%PDF-1.4"))
    assert storage.exists(key)
    storage.delete_entity(UPLOADS, "doc3")
    assert not storage.exists(key)


def test_write_bytes_and_read_roundtrip(tmp_path):
    storage = LocalStorageProvider(tmp_path)
    key = storage.write_bytes("outputs", "job1", "document.md", b"# Title")
    with storage.open_read(key) as fh:
        assert fh.read() == b"# Title"


def test_scratch_dir_is_private_per_entity(tmp_path):
    storage = LocalStorageProvider(tmp_path)
    scratch = storage.scratch_dir("job-xyz")
    assert scratch.exists()
    assert scratch.is_relative_to(tmp_path)
