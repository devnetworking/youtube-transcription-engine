"""PDF -> Markdown conversion pipeline (sections 6-15, 27, 76).

Ties together pdf_engine (extraction), structure.py (classification),
markdown_builder (rendering) and ocr.py (scanned-page fallback) into
one job. Kept as its own service, separate from merge/split, per
section 26.
"""

from __future__ import annotations

import json
import time
import uuid
import zipfile

from ..config import DocumentSettings
from ..exceptions import DocumentNotFoundError
from ..job_queue import CancelToken, JobTarget
from ..markdown_builder import build_markdown, build_text
from ..models import (
    ConversionMetadata,
    ConversionOptions,
    Document,
    DocumentJob,
    DocumentOutput,
    JobOperation,
    OutputType,
    PipelineStage,
)
from ..ocr import get_ocr_provider
from ..pdf_engine import open_pdf
from ..repository import DocumentRepository, now_iso
from ..storage import OUTPUTS, StorageProvider
from ..structure import analyze_document

STAGE_DEFS = [
    ("validate", "Validating document"),
    ("extract", "Extracting content"),
    ("ocr", "Running OCR"),
    ("structure", "Analyzing structure"),
    ("markdown", "Generating Markdown"),
    ("package", "Packaging output"),
]


class PDFToMarkdownService:
    def __init__(self, storage: StorageProvider, repository: DocumentRepository, settings: DocumentSettings):
        self.storage = storage
        self.repository = repository
        self.settings = settings

    def create_job(self, document: Document, options: ConversionOptions) -> DocumentJob:
        stages = [PipelineStage(key=k, label=label) for k, label in STAGE_DEFS]
        job = DocumentJob(
            id=uuid.uuid4().hex,
            operation=JobOperation.PDF_TO_MARKDOWN,
            stages=stages,
            input_document_ids=[document.id],
            options=options.model_dump(),
            created_at=now_iso(),
        )
        self.repository.create_job(job)
        self.repository.audit("PDF_CONVERSION_QUEUED", job.id, document.original_name)
        return job

    def build_target(self, job: DocumentJob) -> JobTarget:
        document_id = job.input_document_ids[0]
        options = ConversionOptions(**job.options)

        def target(token: CancelToken) -> None:
            stages = [PipelineStage(**s.model_dump()) for s in job.stages]
            document = self.repository.get_document(document_id)
            if document is None:
                raise DocumentNotFoundError(f"Document '{document_id}' was not found.")

            start = time.monotonic()
            token.set_stage(stages, "validate", 0.02)
            token.check()

            asset_counter = {"n": 0}

            def write_asset(data: bytes, ext: str) -> str:
                asset_counter["n"] += 1
                filename = f"assets/image-{asset_counter['n']:03d}.{ext}"
                self.storage.write_bytes(OUTPUTS, job.id, filename, data)
                return filename

            ocr_used_pages: set[int] = set()
            ocr_unavailable_pages = 0
            ocr_provider = get_ocr_provider(options.ocr_mode) if options.ocr_mode != "never" else None
            ocr_started = False

            def ocr_page_text(page_index: int):
                nonlocal ocr_started, ocr_unavailable_pages
                if ocr_provider is None:
                    return None
                if not ocr_provider.is_available():
                    ocr_unavailable_pages += 1
                    return None
                if not ocr_started:
                    token.set_stage(stages, "ocr", 0.3)
                    ocr_started = True
                image_bytes = pdf.render_page_image(page_index)
                text = ocr_provider.recognize(image_bytes, options.language)
                if text.strip():
                    ocr_used_pages.add(page_index)
                return text

            with open_pdf(self.storage.abs_path(document.storage_key)) as pdf:
                token.set_stage(stages, "extract", 0.10)
                token.check()

                page_count = pdf.page_count
                progress_step = max(1, page_count // 50)

                def on_page(index: int, total: int) -> None:
                    token.check()
                    if index % progress_step == 0 or index == total - 1:
                        fraction = 0.35 + 0.35 * ((index + 1) / max(total, 1))
                        token.set_stage(stages, "structure", fraction)

                block_iter = analyze_document(
                    pdf,
                    extract_images=options.extract_images,
                    extract_links=options.extract_links,
                    ocr_page_text=ocr_page_text,
                    on_page=on_page,
                    min_image_dim=120 if options.ignore_decorative_images else 60,
                    detect_headings=options.detect_headings,
                    preserve_lists=options.preserve_lists,
                    detect_tables=options.detect_tables,
                )
                # A materialized list is only needed when a second render
                # pass (plain text export) will also consume the blocks;
                # otherwise stay a generator so image bytes for page N are
                # written to disk and freed before page N+1 is analyzed.
                blocks = list(block_iter) if options.generate_txt else block_iter

                token.set_stage(stages, "markdown", 0.72)
                markdown_text, stats = build_markdown(
                    blocks, write_asset,
                    extract_images=options.extract_images,
                    preserve_page_references=options.preserve_page_references,
                )
                txt_text = build_text(blocks) if options.generate_txt else None

            token.set_stage(stages, "package", 0.9)
            token.check()

            outputs_created: list[DocumentOutput] = []
            md_bytes = markdown_text.encode("utf-8")
            md_key = self.storage.write_bytes(OUTPUTS, job.id, "document.md", md_bytes)
            outputs_created.append(DocumentOutput(
                id=uuid.uuid4().hex, job_id=job.id, output_type=OutputType.MARKDOWN,
                storage_key=md_key, filename="document.md", file_size=len(md_bytes), created_at=now_iso(),
            ))

            if txt_text:
                txt_bytes = txt_text.encode("utf-8")
                txt_key = self.storage.write_bytes(OUTPUTS, job.id, "document.txt", txt_bytes)
                outputs_created.append(DocumentOutput(
                    id=uuid.uuid4().hex, job_id=job.id, output_type=OutputType.TEXT,
                    storage_key=txt_key, filename="document.txt", file_size=len(txt_bytes), created_at=now_iso(),
                ))

            duration = time.monotonic() - start
            conversion_meta = ConversionMetadata(
                source_file=document.original_name,
                pages=page_count,
                processing_time_seconds=round(duration, 2),
                ocr_used=bool(ocr_used_pages),
                images_extracted=stats.images_written,
                tables_detected=stats.tables_rendered,
                conversion_engine="PyMuPDF",
                created_at=now_iso(),
            )
            if options.generate_metadata:
                meta_bytes = json.dumps(conversion_meta.model_dump(), indent=2).encode("utf-8")
                meta_key = self.storage.write_bytes(OUTPUTS, job.id, "metadata.json", meta_bytes)
                outputs_created.append(DocumentOutput(
                    id=uuid.uuid4().hex, job_id=job.id, output_type=OutputType.METADATA,
                    storage_key=meta_key, filename="metadata.json", file_size=len(meta_bytes), created_at=now_iso(),
                ))

            if stats.images_written > 0 or txt_text is not None or options.generate_metadata:
                output_dir = self.storage.abs_path(f"{OUTPUTS}/{job.id}")
                zip_path = output_dir / "package.zip"
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for path in output_dir.rglob("*"):
                        if path.is_file() and path.name != "package.zip":
                            zf.write(path, arcname=str(path.relative_to(output_dir)))
                outputs_created.append(DocumentOutput(
                    id=uuid.uuid4().hex, job_id=job.id, output_type=OutputType.ZIP,
                    storage_key=f"{OUTPUTS}/{job.id}/package.zip", filename="package.zip",
                    file_size=zip_path.stat().st_size, created_at=now_iso(),
                ))

            for output in outputs_created:
                self.repository.create_output(output)

            warnings = []
            if ocr_unavailable_pages > 0:
                warnings.append(
                    f"Conversion completed, but {ocr_unavailable_pages} scanned page(s) require OCR, "
                    "which is not installed. Install Tesseract and retry to recover that text."
                )
            if stats.garbled_chars > 0:
                warnings.append(
                    f"{stats.garbled_chars} character(s) could not be read from this PDF's fonts and were "
                    "dropped rather than guessed. This is a limitation of the source file's font encoding, "
                    "not of the conversion."
                )

            self.repository.update_job(job.id, result_summary={
                "pages": page_count,
                "headings": stats.headings,
                "tables_detected": stats.tables_rendered,
                "images_extracted": stats.images_written,
                "ocr_used": bool(ocr_used_pages),
                "ocr_pages": len(ocr_used_pages),
                "warnings": warnings,
            })
            token.finish_stages(stages)
            self.repository.audit("PDF_CONVERTED", job.id, document.original_name)

        return target
