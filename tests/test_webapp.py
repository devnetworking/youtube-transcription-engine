import pytest

from src import webapp
from src.models import QualityLevel, VideoOutcome


class _SyncThread:
    """Runs the target immediately instead of on a real thread, so tests
    don't need to poll/sleep waiting for a background job to finish."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(webapp.threading, "Thread", _SyncThread)
    webapp._jobs.clear()
    app = webapp.create_app(tmp_path)
    app.testing = True
    return app.test_client()


def test_index_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Transcrire" in resp.data or b"url" in resp.data.lower()


def test_create_job_requires_url(client):
    resp = client.post("/api/jobs", json={"url": ""})
    assert resp.status_code == 400


def test_successful_job_exposes_files(monkeypatch, client, tmp_path):
    video_dir = tmp_path / "Some_Video"
    video_dir.mkdir()
    (video_dir / "transcript.md").write_text("# Some Video\ncontent", encoding="utf-8")
    (video_dir / "transcript.txt").write_text("Some Video\ncontent", encoding="utf-8")

    def fake_process_video(url, config, output_root, report=None):
        report("[1/6] Reading YouTube metadata...", "step")
        report("Complete", "success")
        return VideoOutcome(
            success=True,
            video_dir=str(video_dir),
            title="Some Video",
            quality=QualityLevel.HIGH,
            source="Manual captions",
        )

    monkeypatch.setattr(webapp, "process_video", fake_process_video)

    resp = client.post("/api/jobs", json={"url": "https://www.youtube.com/watch?v=abc123"})
    assert resp.status_code == 201
    job_id = resp.get_json()["jobs"][0]["id"]

    status = client.get(f"/api/jobs/{job_id}").get_json()
    assert status["status"] == "success"
    assert "transcript.md" in status["files"]
    assert any(entry["level"] == "success" for entry in status["logs"])

    file_resp = client.get(f"/api/jobs/{job_id}/file/transcript.md")
    assert file_resp.status_code == 200
    assert b"Some Video" in file_resp.data


def test_failed_job_reports_no_files(monkeypatch, client):
    def fake_process_video(url, config, output_root, report=None):
        report("Failed to read video metadata: bad url", "error")
        return VideoOutcome(success=False, errors=["bad url"])

    monkeypatch.setattr(webapp, "process_video", fake_process_video)

    resp = client.post("/api/jobs", json={"url": "not a url"})
    job_id = resp.get_json()["jobs"][0]["id"]

    status = client.get(f"/api/jobs/{job_id}").get_json()
    assert status["status"] == "failed"
    assert status["files"] == []


def test_file_endpoint_rejects_disallowed_filename(monkeypatch, client, tmp_path):
    video_dir = tmp_path / "Vid"
    video_dir.mkdir()
    (video_dir.parent / "secret.txt").write_text("nope", encoding="utf-8")

    def fake_process_video(url, config, output_root, report=None):
        return VideoOutcome(success=True, video_dir=str(video_dir), title="Vid")

    monkeypatch.setattr(webapp, "process_video", fake_process_video)

    resp = client.post("/api/jobs", json={"url": "https://www.youtube.com/watch?v=abc123"})
    job_id = resp.get_json()["jobs"][0]["id"]

    # Attempted traversal / non-whitelisted filenames must never be served.
    traversal = client.get(f"/api/jobs/{job_id}/file/..%2Fsecret.txt")
    assert traversal.status_code == 404

    unknown = client.get(f"/api/jobs/{job_id}/file/secret.txt")
    assert unknown.status_code == 404


def test_unknown_job_id_returns_404(client):
    resp = client.get("/api/jobs/does-not-exist")
    assert resp.status_code == 404


def test_playlist_url_creates_one_job_per_video(monkeypatch, client):
    monkeypatch.setattr(
        webapp,
        "resolve_urls",
        lambda urls, report=None, verbose=False: [
            "https://www.youtube.com/watch?v=aaaaaaaaaaa",
            "https://www.youtube.com/watch?v=bbbbbbbbbbb",
        ],
    )

    calls = []

    def fake_process_video(url, config, output_root, report=None):
        calls.append(url)
        return VideoOutcome(success=True, video_dir=str(output_root / url[-5:]), title=url)

    monkeypatch.setattr(webapp, "process_video", fake_process_video)

    resp = client.post("/api/jobs", json={"url": "https://www.youtube.com/playlist?list=PLxyz"})
    assert resp.status_code == 201
    jobs = resp.get_json()["jobs"]
    assert len(jobs) == 2
    assert len(calls) == 2
    assert {j["url"] for j in jobs} == set(calls)
