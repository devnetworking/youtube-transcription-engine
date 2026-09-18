"""HTTP surface for the Documents module (section 49).

The only file in this module that imports Flask - every service stays
framework-agnostic and unit-testable without a request context. Mirrors
webapp.py's own posture: local, single-user, no auth (see AGENTS note
in webapp.py) - the same trust boundary already accepted for the
YouTube tool applies here, since both bind to 127.0.0.1 by default.
"""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, Response, jsonify, render_template, request, send_file

from .cleanup import run_retention_cleanup
from .config import DocumentSettings
from .exceptions import (
    DocumentError,
    DocumentNotFoundError,
    InvalidUploadError,
    JobNotFoundError,
    PageRangeError,
    PathSecurityError,
    ResourceLimitError,
    YouTubeError,
)
from .job_queue import JobQueue
from .models import (
    ConversionOptions,
    JobOperation,
    MergeInput,
    MergeOptions,
    OutputType,
    SplitMode,
    SplitOptions,
    YouTubeTranscriptOptions,
)
from .repository import DocumentRepository
from .services.document_service import DocumentService
from .services.job_service import JobService
from .services.merge_service import MergeService
from .services.pdf_to_markdown_service import PDFToMarkdownService
from .services.preview_service import PreviewService
from .services.split_service import SplitService
from .services.youtube_transcript_service import YouTubeTranscriptService
from .storage import LocalStorageProvider

logger = logging.getLogger("documents")

_ERROR_STATUS = {
    InvalidUploadError: 400,
    PageRangeError: 400,
    ResourceLimitError: 413,
    PathSecurityError: 400,
    DocumentNotFoundError: 404,
    JobNotFoundError: 404,
}


def _error_response(exc: Exception) -> tuple[Response, int]:
    status = _ERROR_STATUS.get(type(exc), 400 if isinstance(exc, DocumentError) else 500)
    if status == 500:
        logger.exception("Unexpected error in documents module")
        message = "An unexpected error occurred while processing your request."
        body = {"error": message}
    else:
        message = str(exc)
        body = {"error": message}
        if isinstance(exc, YouTubeError):
            body["error_code"] = exc.code
    return jsonify(body), status


def create_documents_blueprint(data_root: Path, settings: DocumentSettings) -> Blueprint:
    storage = LocalStorageProvider(data_root)
    repository = DocumentRepository(data_root / "documents.db")
    run_retention_cleanup(repository, storage, settings)
    job_queue = JobQueue(repository, max_workers=settings.max_concurrent_jobs, job_timeout_seconds=settings.job_timeout_seconds)

    document_service = DocumentService(storage, repository, settings)
    preview_service = PreviewService(storage, repository, settings)
    pdf_to_markdown_service = PDFToMarkdownService(storage, repository, settings)
    merge_service = MergeService(storage, repository, settings)
    split_service = SplitService(storage, repository, settings)
    youtube_transcript_service = YouTubeTranscriptService(storage, repository, settings)
    job_service = JobService(repository, job_queue, {
        JobOperation.PDF_TO_MARKDOWN: pdf_to_markdown_service,
        JobOperation.MERGE: merge_service,
        JobOperation.SPLIT: split_service,
        JobOperation.YOUTUBE_TRANSCRIPT: youtube_transcript_service,
    }, storage)

    bp = Blueprint("documents", __name__, url_prefix="/api")

    # -- documents -------------------------------------------------------

    @bp.post("/documents/upload")
    def upload_documents():
        files = request.files.getlist("file") or request.files.getlist("files")
        if not files:
            return jsonify({"error": "Attach at least one PDF file."}), 400

        created, errors = [], []
        for file_storage in files:
            try:
                document = document_service.ingest_upload(file_storage.stream, file_storage.filename or "document.pdf")
                created.append(document.model_dump(mode="json"))
            except DocumentError as exc:
                errors.append({"filename": file_storage.filename, "error": str(exc)})
            except Exception:
                logger.exception("Unexpected error ingesting upload %s", file_storage.filename)
                errors.append({"filename": file_storage.filename, "error": "This file could not be processed."})

        status = 201 if created else 400
        return jsonify({"documents": created, "errors": errors}), status

    @bp.get("/documents")
    def list_documents():
        search = request.args.get("search") or None
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = int(request.args.get("offset", 0))
        docs = document_service.list(search=search, limit=limit, offset=offset)
        return jsonify({
            "documents": [d.model_dump(mode="json") for d in docs],
            "total": document_service.count(),
        })

    @bp.get("/documents/<document_id>")
    def get_document(document_id: str):
        try:
            document = document_service.get(document_id)
        except DocumentError as exc:
            return _error_response(exc)
        jobs = document_service.related_jobs(document)
        return jsonify({
            "document": document.model_dump(mode="json"),
            "jobs": [j.model_dump(mode="json") for j in jobs],
        })

    @bp.patch("/documents/<document_id>")
    def rename_document(document_id: str):
        payload = request.get_json(silent=True) or {}
        new_name = (payload.get("original_name") or "").strip()
        if not new_name:
            return jsonify({"error": "A new name is required."}), 400
        try:
            document = document_service.rename(document_id, new_name)
        except DocumentError as exc:
            return _error_response(exc)
        return jsonify({"document": document.model_dump(mode="json")})

    @bp.delete("/documents/<document_id>")
    def delete_document(document_id: str):
        try:
            document_service.delete(document_id)
        except DocumentError as exc:
            return _error_response(exc)
        return jsonify({"ok": True})

    @bp.get("/documents/<document_id>/download")
    def download_document(document_id: str):
        try:
            document = document_service.get(document_id)
        except DocumentError as exc:
            return _error_response(exc)
        as_attachment = document.mime_type == "application/pdf"
        return send_file(
            storage.abs_path(document.storage_key),
            mimetype=document.mime_type,
            as_attachment=as_attachment,
            download_name=document.original_name,
        )

    @bp.get("/documents/<document_id>/thumbnail/<int:page_index>")
    def get_thumbnail(document_id: str, page_index: int):
        max_dim = min(int(request.args.get("size", 320)), 1200)
        try:
            data = preview_service.get_thumbnail(document_id, page_index, max_dim)
        except DocumentError as exc:
            return _error_response(exc)
        return Response(data, mimetype="image/png")

    @bp.get("/documents/<document_id>/derived")
    def derived_files(document_id: str):
        try:
            document_service.get(document_id)
        except DocumentError as exc:
            return _error_response(exc)
        jobs, outputs = document_service.derived_outputs(document_id)
        return jsonify({
            "jobs": [j.model_dump(mode="json") for j in jobs],
            "outputs": [o.model_dump(mode="json") for o in outputs],
        })

    # -- conversion / merge / split ---------------------------------------

    @bp.post("/documents/convert/markdown")
    def convert_to_markdown():
        payload = request.get_json(silent=True) or {}
        document_ids = payload.get("document_ids") or ([payload["document_id"]] if payload.get("document_id") else [])
        if not document_ids:
            return jsonify({"error": "document_id (or document_ids) is required."}), 400
        options = ConversionOptions(**(payload.get("options") or {}))

        jobs = []
        for document_id in document_ids:
            try:
                document = document_service.get(document_id)
                job = pdf_to_markdown_service.create_job(document, options)
                job_service.submit(job)
                jobs.append(job.model_dump(mode="json"))
            except DocumentError as exc:
                return _error_response(exc)
        return jsonify({"jobs": jobs}), 201

    @bp.post("/documents/merge")
    def merge_documents():
        payload = request.get_json(silent=True) or {}
        try:
            options = MergeOptions(
                inputs=[MergeInput(**i) for i in payload.get("inputs", [])],
                output_name=payload.get("output_name"),
            )
            job = merge_service.create_job(options)
            job_service.submit(job)
        except DocumentError as exc:
            return _error_response(exc)
        return jsonify({"job": job.model_dump(mode="json")}), 201

    @bp.post("/documents/split")
    def split_document():
        payload = request.get_json(silent=True) or {}
        try:
            options = SplitOptions(
                document_id=payload["document_id"],
                mode=SplitMode(payload.get("mode", "ranges")),
                ranges=payload.get("ranges"),
                every_n_pages=payload.get("every_n_pages"),
                naming_pattern=payload.get("naming_pattern") or SplitOptions.model_fields["naming_pattern"].default,
            )
            job = split_service.create_job(options)
            job_service.submit(job)
        except KeyError:
            return jsonify({"error": "document_id is required."}), 400
        except DocumentError as exc:
            return _error_response(exc)
        return jsonify({"job": job.model_dump(mode="json")}), 201

    # -- youtube transcript --------------------------------------------------

    @bp.post("/youtube/preview")
    def youtube_preview():
        payload = request.get_json(silent=True) or {}
        url = (payload.get("url") or "").strip()
        if not url:
            return jsonify({"error": "A YouTube URL is required."}), 400
        try:
            return jsonify(youtube_transcript_service.preview(url))
        except DocumentError as exc:
            return _error_response(exc)

    @bp.post("/documents/youtube-transcript")
    def create_youtube_transcript():
        payload = request.get_json(silent=True) or {}
        url = (payload.get("url") or "").strip()
        if not url:
            return jsonify({"error": "A YouTube URL is required."}), 400
        options_payload = payload.get("options") or {}
        try:
            options = YouTubeTranscriptOptions(url=url, **options_payload)
            jobs = youtube_transcript_service.create_jobs(options)
            for job in jobs:
                job_service.submit(job)
        except DocumentError as exc:
            return _error_response(exc)
        return jsonify({"jobs": [j.model_dump(mode="json") for j in jobs]}), 201

    # -- jobs --------------------------------------------------------------

    @bp.get("/document-jobs")
    def list_jobs():
        status = request.args.get("status")
        operation = request.args.get("operation")
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = int(request.args.get("offset", 0))
        jobs = job_service.list(status=status, operation=operation, limit=limit, offset=offset)
        return jsonify({"jobs": [j.model_dump(mode="json") for j in jobs]})

    @bp.get("/document-jobs/<job_id>")
    def get_job(job_id: str):
        try:
            job = job_service.get(job_id)
            outputs = job_service.outputs(job_id)
        except DocumentError as exc:
            return _error_response(exc)
        return jsonify({
            "job": job.model_dump(mode="json"),
            "outputs": [o.model_dump(mode="json") for o in outputs],
        })

    @bp.post("/document-jobs/<job_id>/retry")
    def retry_job(job_id: str):
        try:
            job = job_service.retry(job_id)
        except DocumentError as exc:
            return _error_response(exc)
        return jsonify({"job": job.model_dump(mode="json")})

    @bp.post("/document-jobs/<job_id>/cancel")
    def cancel_job(job_id: str):
        try:
            job = job_service.cancel(job_id)
        except DocumentError as exc:
            return _error_response(exc)
        return jsonify({"job": job.model_dump(mode="json")})

    @bp.delete("/document-jobs/<job_id>")
    def delete_job(job_id: str):
        try:
            job_service.delete(job_id)
        except DocumentError as exc:
            return _error_response(exc)
        return jsonify({"ok": True})

    @bp.post("/document-jobs/<job_id>/repeat")
    def repeat_job(job_id: str):
        try:
            old_job = job_service.get(job_id)
            if old_job.operation == JobOperation.PDF_TO_MARKDOWN:
                document = document_service.get(old_job.input_document_ids[0])
                new_job = pdf_to_markdown_service.create_job(document, ConversionOptions(**old_job.options))
            elif old_job.operation == JobOperation.MERGE:
                new_job = merge_service.create_job(MergeOptions(**old_job.options))
            elif old_job.operation == JobOperation.SPLIT:
                new_job = split_service.create_job(SplitOptions(**old_job.options))
            else:
                new_job = youtube_transcript_service.create_jobs(YouTubeTranscriptOptions(**old_job.options))[0]
            job_service.submit(new_job)
        except DocumentError as exc:
            return _error_response(exc)
        return jsonify({"job": new_job.model_dump(mode="json")}), 201

    @bp.get("/document-jobs/<job_id>/download/<output_id>")
    def download_output(job_id: str, output_id: str):
        try:
            job_service.get(job_id)
            output = repository.get_output(output_id)
        except DocumentError as exc:
            return _error_response(exc)
        if output is None or output.job_id != job_id:
            return jsonify({"error": "Output not found."}), 404
        mimetype = "text/plain; charset=utf-8" if output.filename.endswith((".md", ".txt")) else None
        try:
            path = storage.abs_path(output.storage_key)
        except PathSecurityError as exc:
            return _error_response(exc)
        return send_file(path, mimetype=mimetype, as_attachment=mimetype is None, download_name=output.filename)

    @bp.get("/document-jobs/<job_id>/preview")
    def preview_markdown(job_id: str):
        try:
            job_service.get(job_id)
            outputs = job_service.outputs(job_id)
        except DocumentError as exc:
            return _error_response(exc)
        markdown_output = next((o for o in outputs if o.output_type == OutputType.MARKDOWN), None)
        if markdown_output is None:
            return jsonify({"error": "This job has no Markdown output yet."}), 404
        with storage.open_read(markdown_output.storage_key) as fh:
            content = fh.read().decode("utf-8", errors="replace")
        return jsonify({"markdown": content})

    # -- dashboard -----------------------------------------------------------

    @bp.get("/documents-overview")
    def overview():
        stats = repository.overview_stats()
        stats["recent_documents"] = [d.model_dump(mode="json") for d in stats["recent_documents"]]
        stats["recent_jobs"] = [j.model_dump(mode="json") for j in stats["recent_jobs"]]
        return jsonify(stats)

    @bp.get("/documents-settings")
    def get_settings():
        return jsonify(settings.model_dump())

    return bp


def create_documents_pages_blueprint() -> Blueprint:
    """Server-rendered page shells (section 3, 69, 70): each route has
    one clear job and loads its own JS module, which talks to the JSON
    API above. No SPA framework/build step - same approach as the
    existing index.html, just organized into one page per screen
    instead of one big page, per section 69."""
    bp = Blueprint("documents_pages", __name__, url_prefix="/documents")

    @bp.get("/pdf-to-markdown")
    def pdf_to_markdown_page():
        return render_template("documents/pdf_to_markdown.html")

    @bp.get("/merge")
    def merge_page():
        return render_template("documents/merge.html")

    @bp.get("/split")
    def split_page():
        return render_template("documents/split.html")

    @bp.get("/youtube-transcript")
    def youtube_transcript_page():
        return render_template("documents/youtube_transcript.html")

    @bp.get("/jobs")
    def jobs_page():
        return render_template("documents/jobs.html")

    @bp.get("/files")
    def files_page():
        return render_template("documents/files.html")

    @bp.get("/files/<document_id>")
    def file_detail_page(document_id: str):
        return render_template("documents/file_detail.html", document_id=document_id)

    @bp.get("/history")
    def history_page():
        return render_template("documents/history.html")

    @bp.get("/settings")
    def settings_page():
        return render_template("documents/settings.html")

    return bp
