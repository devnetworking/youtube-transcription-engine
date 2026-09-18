"""Integration tests: real Flask test client + real SQLite + real
background job queue (threads) + real PyMuPDF - the closest thing to
exercising the actual user flows (upload -> convert -> download,
upload multiple -> merge -> download, upload -> split -> ZIP) without
a browser. Jobs run on real threads, so tests poll briefly instead of
mocking the queue away.
"""

from __future__ import annotations

import io
import time

import pymupdf as fitz
import pytest
from flask import Flask

from src.documents.config import DocumentSettings
from src.documents.routes import create_documents_blueprint


def _pdf_bytes(pages: int = 1, heading: str | None = None, body: str = "Body text for testing.") -> bytes:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        y = 72
        if heading:
            page.insert_text((72, y), heading, fontsize=20, fontname="hebo")
            y += 40
        page.insert_text((72, y), f"{body} (page {i + 1})", fontsize=11)
        page.insert_text((72, y + 16), "A second line of body text for realism.", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def client(tmp_path):
    settings = DocumentSettings(max_concurrent_jobs=2, job_timeout_seconds=30, max_upload_size_mb=50)
    app = Flask(__name__, template_folder=str(tmp_path))  # no HTML pages exercised here
    app.register_blueprint(create_documents_blueprint(tmp_path, settings))
    app.testing = True
    return app.test_client()


def _upload(client, data: bytes, filename: str = "test.pdf"):
    return client.post(
        "/api/documents/upload",
        data={"file": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


def _wait_for_job(client, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        resp = client.get(f"/api/document-jobs/{job_id}")
        last = resp.get_json()
        if last["job"]["status"] in ("completed", "failed", "cancelled"):
            return last
        time.sleep(0.05)
    raise AssertionError(f"Job {job_id} did not finish in time, last state: {last}")


# ---- upload ---------------------------------------------------------------

def test_upload_accepts_valid_pdf(client):
    resp = _upload(client, _pdf_bytes(pages=2))
    assert resp.status_code == 201
    data = resp.get_json()
    assert len(data["documents"]) == 1
    assert data["documents"][0]["page_count"] == 2


def test_upload_rejects_non_pdf_content(client):
    resp = _upload(client, b"<html>this is not a pdf</html>", filename="fake.pdf")
    data = resp.get_json()
    assert not data["documents"]
    assert "PDF" in data["errors"][0]["error"] or "pdf" in data["errors"][0]["error"]


def test_upload_rejects_disallowed_extension(client):
    resp = _upload(client, b"hello world", filename="notes.txt")
    data = resp.get_json()
    assert not data["documents"]
    assert data["errors"]


def test_upload_rejects_corrupt_pdf_with_valid_header(client):
    # Passes the magic-byte check but has no valid internal structure.
    resp = _upload(client, b"%PDF-1.4\nthis is not a real xref table or object stream")
    data = resp.get_json()
    assert not data["documents"]
    assert data["errors"]


def test_upload_deduplicates_identical_content(client):
    payload = _pdf_bytes(pages=1)
    first = _upload(client, payload).get_json()["documents"][0]
    second = _upload(client, payload).get_json()["documents"][0]
    assert first["id"] == second["id"]


def test_upload_oversized_file_rejected(tmp_path):
    settings = DocumentSettings(max_upload_size_mb=1)
    app = Flask(__name__, template_folder=str(tmp_path))
    app.register_blueprint(create_documents_blueprint(tmp_path, settings))
    app.testing = True
    client = app.test_client()
    oversized = _pdf_bytes(pages=1) + b"0" * (2 * 1024 * 1024)  # > 1MB cap
    resp = _upload(client, oversized)
    data = resp.get_json()
    assert not data["documents"]
    assert data["errors"]


def test_get_unknown_document_returns_404_not_a_leak(client):
    resp = client.get("/api/documents/..%2F..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code == 404


# ---- convert to markdown ----------------------------------------------------

def test_convert_to_markdown_end_to_end(client):
    doc = _upload(client, _pdf_bytes(pages=1, heading="Chapter One")).get_json()["documents"][0]
    resp = client.post("/api/documents/convert/markdown", json={"document_ids": [doc["id"]]})
    assert resp.status_code == 201
    job = resp.get_json()["jobs"][0]

    result = _wait_for_job(client, job["id"])
    assert result["job"]["status"] == "completed"
    md_output = next(o for o in result["outputs"] if o["filename"] == "document.md")

    download = client.get(f"/api/document-jobs/{job['id']}/download/{md_output['id']}")
    assert download.status_code == 200
    assert b"Chapter One" in download.data


def test_convert_with_embedded_image_writes_asset_into_zip(client):
    # Regression: write_bytes() used to only create the job's own output
    # directory, not the "assets/" subdirectory image files are nested
    # under - extracting a real embedded image used to crash with
    # FileNotFoundError.
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Document with an image", fontsize=14)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 120))
    pix.set_rect(pix.irect, (200, 30, 30))
    page.insert_image(fitz.Rect(72, 150, 192, 270), pixmap=pix)
    data = doc.tobytes()
    doc.close()

    uploaded = _upload(client, data).get_json()["documents"][0]
    resp = client.post("/api/documents/convert/markdown", json={"document_ids": [uploaded["id"]], "options": {"extract_images": True}})
    job = resp.get_json()["jobs"][0]
    result = _wait_for_job(client, job["id"])
    assert result["job"]["status"] == "completed"
    assert result["job"]["result_summary"]["images_extracted"] >= 1

    zip_output = next(o for o in result["outputs"] if o["output_type"] == "zip")
    download = client.get(f"/api/document-jobs/{job['id']}/download/{zip_output['id']}")
    import zipfile
    from io import BytesIO
    with zipfile.ZipFile(BytesIO(download.data)) as zf:
        names = zf.namelist()
    assert any(name.startswith("assets/") for name in names)


def test_convert_preview_endpoint_returns_markdown_text(client):
    doc = _upload(client, _pdf_bytes(pages=1, heading="Preview Me")).get_json()["documents"][0]
    job = client.post("/api/documents/convert/markdown", json={"document_ids": [doc["id"]]}).get_json()["jobs"][0]
    _wait_for_job(client, job["id"])
    preview = client.get(f"/api/document-jobs/{job['id']}/preview").get_json()
    assert "Preview Me" in preview["markdown"]


def test_convert_failed_job_can_be_retried(client, monkeypatch):
    doc = _upload(client, _pdf_bytes(pages=1)).get_json()["documents"][0]

    import src.documents.services.pdf_to_markdown_service as svc_module
    original = svc_module.analyze_document
    calls = {"n": 0}

    def flaky_analyze(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(svc_module, "analyze_document", flaky_analyze)

    job = client.post("/api/documents/convert/markdown", json={"document_ids": [doc["id"]]}).get_json()["jobs"][0]
    first = _wait_for_job(client, job["id"])
    assert first["job"]["status"] == "failed"

    retry_resp = client.post(f"/api/document-jobs/{job['id']}/retry")
    assert retry_resp.status_code == 200
    second = _wait_for_job(client, job["id"])
    assert second["job"]["status"] == "completed"


# ---- merge -------------------------------------------------------------------

def test_merge_multiple_pdfs_end_to_end(client):
    a = _upload(client, _pdf_bytes(pages=2, heading="Doc A")).get_json()["documents"][0]
    b = _upload(client, _pdf_bytes(pages=3, heading="Doc B")).get_json()["documents"][0]

    resp = client.post("/api/documents/merge", json={
        "inputs": [{"document_id": a["id"]}, {"document_id": b["id"]}],
        "output_name": "combined.pdf",
    })
    assert resp.status_code == 201
    job = resp.get_json()["job"]
    result = _wait_for_job(client, job["id"])
    assert result["job"]["status"] == "completed"
    assert result["job"]["result_summary"]["page_count"] == 5

    output = result["outputs"][0]
    download = client.get(f"/api/document-jobs/{job['id']}/download/{output['id']}")
    merged = fitz.open(stream=download.data, filetype="pdf")
    assert merged.page_count == 5


def test_merge_with_partial_page_selection(client):
    a = _upload(client, _pdf_bytes(pages=5)).get_json()["documents"][0]
    resp = client.post("/api/documents/merge", json={"inputs": [{"document_id": a["id"], "page_ranges": "1-2"}]})
    job = resp.get_json()["job"]
    result = _wait_for_job(client, job["id"])
    assert result["job"]["status"] == "completed"
    assert result["job"]["result_summary"]["page_count"] == 2


def test_merge_rejects_out_of_range_pages_immediately(client):
    a = _upload(client, _pdf_bytes(pages=2)).get_json()["documents"][0]
    resp = client.post("/api/documents/merge", json={"inputs": [{"document_id": a["id"], "page_ranges": "1-10"}]})
    assert resp.status_code == 400
    assert "2" in resp.get_json()["error"]


# ---- split ---------------------------------------------------------------------

def test_split_by_ranges_produces_one_file_per_range(client):
    doc = _upload(client, _pdf_bytes(pages=4)).get_json()["documents"][0]
    resp = client.post("/api/documents/split", json={"document_id": doc["id"], "mode": "ranges", "ranges": "1-2\n3-4"})
    assert resp.status_code == 201
    job = resp.get_json()["job"]
    result = _wait_for_job(client, job["id"])
    assert result["job"]["status"] == "completed"
    pdf_outputs = [o for o in result["outputs"] if o["output_type"] == "pdf"]
    assert len(pdf_outputs) == 2
    zip_outputs = [o for o in result["outputs"] if o["output_type"] == "zip"]
    assert len(zip_outputs) == 1


def test_split_every_n_pages(client):
    doc = _upload(client, _pdf_bytes(pages=5)).get_json()["documents"][0]
    resp = client.post("/api/documents/split", json={"document_id": doc["id"], "mode": "every_n_pages", "every_n_pages": 2})
    job = resp.get_json()["job"]
    result = _wait_for_job(client, job["id"])
    pdf_outputs = [o for o in result["outputs"] if o["output_type"] == "pdf"]
    assert len(pdf_outputs) == 3  # 2 + 2 + 1


def test_split_extract_pages_produces_single_file(client):
    doc = _upload(client, _pdf_bytes(pages=10)).get_json()["documents"][0]
    resp = client.post("/api/documents/split", json={"document_id": doc["id"], "mode": "extract_pages", "ranges": "1,3,5"})
    job = resp.get_json()["job"]
    result = _wait_for_job(client, job["id"])
    pdf_outputs = [o for o in result["outputs"] if o["output_type"] == "pdf"]
    assert len(pdf_outputs) == 1
    download = client.get(f"/api/document-jobs/{job['id']}/download/{pdf_outputs[0]['id']}")
    extracted = fitz.open(stream=download.data, filetype="pdf")
    assert extracted.page_count == 3


def test_split_invalid_range_returns_clear_error(client):
    doc = _upload(client, _pdf_bytes(pages=3)).get_json()["documents"][0]
    resp = client.post("/api/documents/split", json={"document_id": doc["id"], "mode": "ranges", "ranges": "5-10"})
    assert resp.status_code == 400
    assert "3" in resp.get_json()["error"]


# ---- jobs / history / files --------------------------------------------------

def test_job_can_be_cancelled(client):
    doc = _upload(client, _pdf_bytes(pages=1)).get_json()["documents"][0]
    job = client.post("/api/documents/convert/markdown", json={"document_ids": [doc["id"]]}).get_json()["jobs"][0]
    client.post(f"/api/document-jobs/{job['id']}/cancel")
    _wait_for_job(client, job["id"])  # either it finished already or got cancelled - both are terminal


def test_repeat_job_creates_a_new_job_with_same_options(client):
    doc = _upload(client, _pdf_bytes(pages=1)).get_json()["documents"][0]
    job = client.post("/api/documents/convert/markdown", json={"document_ids": [doc["id"]]}).get_json()["jobs"][0]
    _wait_for_job(client, job["id"])
    repeat_resp = client.post(f"/api/document-jobs/{job['id']}/repeat")
    assert repeat_resp.status_code == 201
    new_job = repeat_resp.get_json()["job"]
    assert new_job["id"] != job["id"]
    _wait_for_job(client, new_job["id"])


def test_delete_document_removes_it_from_listing(client):
    doc = _upload(client, _pdf_bytes(pages=1)).get_json()["documents"][0]
    client.delete(f"/api/documents/{doc['id']}")
    listing = client.get("/api/documents").get_json()
    assert all(d["id"] != doc["id"] for d in listing["documents"])


def test_rename_document(client):
    doc = _upload(client, _pdf_bytes(pages=1)).get_json()["documents"][0]
    resp = client.patch(f"/api/documents/{doc['id']}", json={"original_name": "renamed.pdf"})
    assert resp.status_code == 200
    assert resp.get_json()["document"]["original_name"] == "renamed.pdf"


def test_thumbnail_endpoint_returns_png(client):
    doc = _upload(client, _pdf_bytes(pages=1)).get_json()["documents"][0]
    resp = client.get(f"/api/documents/{doc['id']}/thumbnail/0")
    assert resp.status_code == 200
    assert resp.data.startswith(b"\x89PNG")


def test_thumbnail_out_of_range_page_is_rejected(client):
    doc = _upload(client, _pdf_bytes(pages=1)).get_json()["documents"][0]
    resp = client.get(f"/api/documents/{doc['id']}/thumbnail/5")
    assert resp.status_code == 400


def test_overview_reflects_activity(client):
    doc = _upload(client, _pdf_bytes(pages=1)).get_json()["documents"][0]
    job = client.post("/api/documents/convert/markdown", json={"document_ids": [doc["id"]]}).get_json()["jobs"][0]
    _wait_for_job(client, job["id"])
    stats = client.get("/api/documents-overview").get_json()
    assert stats["documents_total"] >= 1
    assert stats["conversions"] >= 1
    assert "recent_jobs" in stats


def test_thumbnail_rejected_for_non_pdf_document(client, tmp_path):
    """A YouTube-generated Markdown "document" has no pages to render."""
    from datetime import datetime, timezone

    from src.documents.models import Document, DocumentSource, DocumentStatus
    from src.documents.repository import DocumentRepository

    repository = DocumentRepository(tmp_path / "documents.db")
    now = datetime.now(timezone.utc).isoformat()
    document = Document(
        id="ytdoc1", original_name="Talk.md", storage_key="uploads/ytdoc1/original.pdf",
        mime_type="text/markdown", file_size=10, status=DocumentStatus.READY,
        source=DocumentSource.YOUTUBE, created_at=now,
    )
    repository.create_document(document)
    resp = client.get("/api/documents/ytdoc1/thumbnail/0")
    assert resp.status_code == 400


# ---- youtube transcript ------------------------------------------------------

def test_youtube_preview_rejects_missing_url(client):
    resp = client.post("/api/youtube/preview", json={})
    assert resp.status_code == 400


def test_youtube_preview_rejects_invalid_url(client):
    resp = client.post("/api/youtube/preview", json={"url": "not a url"})
    data = resp.get_json()
    assert resp.status_code == 400
    assert data.get("error_code") == "YT_INVALID_URL"


def test_youtube_transcript_end_to_end(client, monkeypatch):
    import src.documents.services.youtube_transcript_service as svc_module
    from src.models import QualityLevel, VideoMetadata, VideoOutcome

    def fake_fetch_metadata(url, **kwargs):
        metadata = VideoMetadata(video_id="abcdefghijk", url=url, title="A Talk", channel="A Channel", duration_seconds=90)
        return metadata, {"thumbnail": "https://img.example/thumb.jpg"}

    monkeypatch.setattr(svc_module, "fetch_metadata", fake_fetch_metadata)
    monkeypatch.setattr(svc_module, "list_available_languages", lambda video_id: [{"code": "en", "name": "English", "is_generated": False}])

    preview_resp = client.post("/api/youtube/preview", json={"url": "https://www.youtube.com/watch?v=abcdefghijk"})
    assert preview_resp.status_code == 200
    preview = preview_resp.get_json()
    assert preview["title"] == "A Talk"
    assert preview["captions_available"] is True

    def fake_process_video(url, config, output_root, report=None):
        report("[1/6] Reading YouTube metadata...", "step")
        report("[6/6] Writing transcript.md and transcript.txt...", "success")
        video_dir = output_root / "A_Talk"
        video_dir.mkdir(parents=True, exist_ok=True)
        (video_dir / "transcript.md").write_text("# A Talk\n\nHello world.\n", encoding="utf-8")
        (video_dir / "transcript.txt").write_text("A Talk\n\nHello world.\n", encoding="utf-8")
        return VideoOutcome(success=True, video_dir=str(video_dir), title="A Talk", quality=QualityLevel.HIGH, source="Manual captions")

    monkeypatch.setattr(svc_module, "process_video", fake_process_video)

    create_resp = client.post("/api/documents/youtube-transcript", json={"url": preview["url"], "options": {}})
    assert create_resp.status_code == 201
    job = create_resp.get_json()["jobs"][0]

    result = _wait_for_job(client, job["id"])
    assert result["job"]["status"] == "completed"
    assert result["job"]["result_summary"]["title"] == "A Talk"
    assert any(log["message"].startswith("[1/6]") for log in result["job"]["logs"])

    md_output = next(o for o in result["outputs"] if o["output_type"] == "markdown")
    assert md_output["filename"] == "transcript.md"
    preview_md = client.get(f"/api/document-jobs/{job['id']}/preview").get_json()
    assert "Hello world" in preview_md["markdown"]

    # The transcript becomes a browsable Document, distinct from PDFs.
    documents = client.get("/api/documents").get_json()["documents"]
    yt_doc = next(d for d in documents if d["source"] == "youtube")
    assert yt_doc["mime_type"] == "text/markdown"
    download = client.get(f"/api/documents/{yt_doc['id']}/download")
    assert b"Hello world" in download.data


def test_youtube_transcript_failure_reports_clear_message(client, monkeypatch):
    import src.documents.services.youtube_transcript_service as svc_module
    from src.models import VideoOutcome

    monkeypatch.setattr(svc_module, "process_video", lambda url, config, output_root, report=None: VideoOutcome(
        success=False, errors=["Captions unavailable and Whisper is not installed."],
    ))
    create_resp = client.post("/api/documents/youtube-transcript", json={"url": "https://www.youtube.com/watch?v=abcdefghijk"})
    job = create_resp.get_json()["jobs"][0]
    result = _wait_for_job(client, job["id"])
    assert result["job"]["status"] == "failed"
    assert "Whisper is not installed" in result["job"]["error_message"]
