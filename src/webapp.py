"""A small local web UI on top of the same pipeline the CLI uses.

Lets a user paste a YouTube URL into a browser page instead of typing a
command. It runs each transcription in a background thread and exposes
its progress/result over a tiny JSON API that the page polls.

This is a local, single-user tool: no accounts, no auth, and it binds
to 127.0.0.1 by default so it isn't reachable from the network. It is
not meant to be exposed to the internet (spec section 27/28: only
process what the user themselves is authorized to access, and never
turn this into an open relay for arbitrary third parties).
"""

from __future__ import annotations

import argparse
import threading
import uuid
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory

from .config import AppConfig
from .documents.config import DocumentSettings, load_document_settings
from .documents.routes import create_documents_blueprint, create_documents_pages_blueprint
from .pipeline import process_video, resolve_urls

ALLOWED_FILES = [
    "transcript.md",
    "transcript.txt",
    "metadata.json",
    "processing_report.json",
    "chapters.json",
    "raw_transcript.json",
]

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _new_job(url: str) -> str:
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "url": url,
            "status": "queued",
            "logs": [],
            "outcome": None,
        }
    return job_id


def _append_log(job_id: str, message: str, level: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            job["logs"].append({"message": message, "level": level})


def _run_job(job_id: str, url: str, config: AppConfig, output_root: Path) -> None:
    with _jobs_lock:
        _jobs[job_id]["status"] = "running"

    def report(message: str, level: str) -> None:
        _append_log(job_id, message, level)

    try:
        outcome = process_video(url, config, output_root, report=report)
    except Exception as exc:  # noqa: BLE001 - a bug here must not leave the job stuck "running"
        _append_log(job_id, f"Unexpected error: {exc}", "error")
        with _jobs_lock:
            _jobs[job_id]["status"] = "failed"
        return

    with _jobs_lock:
        job = _jobs[job_id]
        job["status"] = "success" if outcome.success else "failed"
        job["outcome"] = outcome.model_dump(mode="json")
        if outcome.video_dir:
            job["video_dir_name"] = Path(outcome.video_dir).name


def create_app(
    output_root: Path,
    defaults: Optional[AppConfig] = None,
    documents_root: Optional[Path] = None,
    documents_settings: Optional[DocumentSettings] = None,
) -> Flask:
    app = Flask(__name__)
    output_root.mkdir(parents=True, exist_ok=True)
    base_config = defaults or AppConfig()

    doc_settings = documents_settings or load_document_settings()
    doc_root = documents_root or (output_root / ".documents")
    doc_root.mkdir(parents=True, exist_ok=True)
    # A generous ceiling on the whole request body (a batch of several
    # PDFs), on top of the per-file limit already enforced while
    # streaming to disk (documents/storage.py) - this just rejects an
    # absurd request before it's even parsed.
    app.config["MAX_CONTENT_LENGTH"] = doc_settings.max_upload_size_mb * 1024 * 1024 * doc_settings.max_files_per_merge
    app.register_blueprint(create_documents_blueprint(doc_root, doc_settings))
    app.register_blueprint(create_documents_pages_blueprint())

    @app.get("/")
    def index():
        # The Documents dashboard is the platform's home page (no
        # redirect chain in the common case - see the "/documents"
        # alias below for anyone who types the old URL directly).
        return render_template("documents/overview.html")

    @app.get("/documents")
    def documents_home_alias():
        return redirect("/")

    @app.get("/legacy/transcribe")
    def legacy_transcribe():
        # The simple, single-page YouTube form this project shipped with
        # before it became part of the Documents workspace. Kept reachable
        # (not deleted) so nothing that worked before stops working, even
        # though /documents/youtube-transcript is now the primary, fully
        # integrated way to do the same thing.
        return render_template("index.html")

    @app.post("/api/jobs")
    def create_job():
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        if not url:
            return jsonify({"error": "A YouTube URL is required."}), 400

        config = base_config.model_copy()
        config.language = data.get("language") or "auto"
        config.whisper_model = data.get("model") or "auto"
        config.force_whisper = bool(data.get("force_whisper", False))
        config.prefer_captions = not config.force_whisper
        config.research_mode = bool(data.get("research_mode", False))
        config.remove_filler_words = bool(data.get("remove_filler_words", False))

        expansion_notes: list[str] = []
        video_urls = resolve_urls(
            [url], report=lambda msg, level: expansion_notes.append(msg), verbose=config.verbose
        )
        if not video_urls:
            return jsonify({"error": "Could not resolve any video from that URL/playlist."}), 400

        jobs = []
        for video_url in video_urls:
            job_id = _new_job(video_url)
            for note in expansion_notes:
                _append_log(job_id, note, "info")
            thread = threading.Thread(
                target=_run_job, args=(job_id, video_url, config, output_root), daemon=True
            )
            thread.start()
            jobs.append({"id": job_id, "url": video_url})

        return jsonify({"jobs": jobs}), 201

    @app.get("/api/jobs/<job_id>")
    def get_job(job_id: str):
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                return jsonify({"error": "Unknown job id."}), 404
            snapshot = {
                "id": job["id"],
                "url": job["url"],
                "status": job["status"],
                "logs": list(job["logs"]),
                "outcome": job["outcome"],
                "files": ALLOWED_FILES if job["status"] == "success" else [],
            }
        return jsonify(snapshot)

    @app.get("/api/jobs/<job_id>/file/<name>")
    def get_job_file(job_id: str, name: str):
        with _jobs_lock:
            job = _jobs.get(job_id)
            video_dir_name = job.get("video_dir_name") if job else None

        if not job or job["status"] != "success" or not video_dir_name:
            return jsonify({"error": "This job has no completed output."}), 404
        if name not in ALLOWED_FILES:
            return jsonify({"error": "Unknown file."}), 404

        video_dir = (output_root / video_dir_name).resolve()
        if not video_dir.is_relative_to(output_root.resolve()):
            return jsonify({"error": "Invalid path."}), 400

        # Serve .md/.txt as plain text so the browser previews them
        # inline instead of forcing a download.
        mimetype = "text/plain; charset=utf-8" if name.endswith((".md", ".txt")) else None
        return send_from_directory(video_dir, name, mimetype=mimetype)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Local web UI for the YouTube transcription engine.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1, local-only).")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000).")
    parser.add_argument("--output", type=Path, default=Path("output"), help="Output directory root.")
    parser.add_argument("--config", type=Path, default=None, help="YAML config file (transcription + documents settings).")
    parser.add_argument("--documents-dir", type=Path, default=None, help="Storage directory for the Documents module (default: <output>/.documents).")
    args = parser.parse_args()

    app = create_app(args.output, documents_root=args.documents_dir, documents_settings=load_document_settings(args.config))
    print(f"Serving on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
