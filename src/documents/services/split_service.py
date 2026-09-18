"""PDF split: page ranges, every N pages, extract a page set, or one PDF
per page (section 19-20)."""

from __future__ import annotations

import uuid
import zipfile

from ..config import DocumentSettings
from ..exceptions import DocumentNotFoundError, PageRangeError
from ..job_queue import CancelToken, JobTarget
from ..models import DocumentJob, DocumentOutput, JobOperation, OutputType, PipelineStage, SplitMode, SplitOptions
from ..pdf_engine import extract_pages
from ..repository import DocumentRepository, now_iso
from ..storage import OUTPUTS, StorageProvider
from ..validation import parse_page_ranges, sanitize_display_name

STAGE_DEFS = [
    ("validate", "Validating document"),
    ("split", "Splitting pages"),
    ("package", "Packaging output"),
]


def _range_groups(spec: str) -> list[str]:
    """RANGES mode accepts one group per line (or semicolon-separated):
    "1-10\\n11-30\\n31-50" -> 3 output files, one per group."""
    return [g.strip() for g in spec.replace(";", "\n").split("\n") if g.strip()]


def _render_name(pattern: str, stem: str, index: int, start_page: int, end_page: int) -> str:
    name = pattern.format(original_name=stem, index=f"{index:02d}", start_page=start_page, end_page=end_page)
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"


class SplitService:
    def __init__(self, storage: StorageProvider, repository: DocumentRepository, settings: DocumentSettings):
        self.storage = storage
        self.repository = repository
        self.settings = settings

    def create_job(self, options: SplitOptions) -> DocumentJob:
        document = self.repository.get_document(options.document_id)
        if document is None:
            raise DocumentNotFoundError(f"Document '{options.document_id}' was not found.")
        page_count = document.page_count or 0

        if options.mode in (SplitMode.RANGES, SplitMode.EXTRACT_PAGES):
            if not options.ranges:
                raise PageRangeError("Enter at least one page range.")
            for group in (_range_groups(options.ranges) if options.mode == SplitMode.RANGES else [options.ranges]):
                parse_page_ranges(group, page_count)
        elif options.mode == SplitMode.EVERY_N_PAGES:
            if not options.every_n_pages or options.every_n_pages < 1:
                raise PageRangeError("Enter how many pages each part should contain (1 or more).")

        stages = [PipelineStage(key=k, label=label) for k, label in STAGE_DEFS]
        job = DocumentJob(
            id=uuid.uuid4().hex,
            operation=JobOperation.SPLIT,
            stages=stages,
            input_document_ids=[document.id],
            options=options.model_dump(mode="json"),
            created_at=now_iso(),
        )
        self.repository.create_job(job)
        self.repository.audit("PDF_SPLIT_QUEUED", job.id, f"mode={options.mode.value}")
        return job

    def build_target(self, job: DocumentJob) -> JobTarget:
        options = SplitOptions(**job.options)

        def target(token: CancelToken) -> None:
            stages = [PipelineStage(**s.model_dump()) for s in job.stages]
            token.set_stage(stages, "validate", 0.05)
            document = self.repository.get_document(options.document_id)
            if document is None:
                raise DocumentNotFoundError(f"Document '{options.document_id}' was not found.")

            page_count = document.page_count or 0
            source_path = self.storage.abs_path(document.storage_key)
            stem = document.original_name.rsplit(".", 1)[0]

            # Each entry: (list of 1-indexed pages, start_page, end_page) for naming.
            groups: list[tuple[list[int], int, int]] = []
            if options.mode == SplitMode.RANGES:
                for group_spec in _range_groups(options.ranges or ""):
                    pages = parse_page_ranges(group_spec, page_count)
                    groups.append((pages, pages[0], pages[-1]))
            elif options.mode == SplitMode.EVERY_N_PAGES:
                n = options.every_n_pages or page_count
                for start in range(1, page_count + 1, n):
                    end = min(start + n - 1, page_count)
                    groups.append((list(range(start, end + 1)), start, end))
            elif options.mode == SplitMode.EXTRACT_PAGES:
                pages = parse_page_ranges(options.ranges or "", page_count)
                groups.append((pages, pages[0], pages[-1]))
            elif options.mode == SplitMode.EVERY_PAGE:
                groups = [([p], p, p) for p in range(1, page_count + 1)]

            token.set_stage(stages, "split", 0.2)
            outputs_created: list[DocumentOutput] = []
            total = len(groups) or 1
            for index, (pages, start_page, end_page) in enumerate(groups, start=1):
                token.check()
                if options.mode == SplitMode.EXTRACT_PAGES:
                    filename = sanitize_display_name(f"{stem}_extracted.pdf")
                else:
                    filename = sanitize_display_name(_render_name(options.naming_pattern, stem, index, start_page, end_page))
                storage_key, output_path = self.storage.reserve_path(OUTPUTS, job.id, filename)
                extract_pages(source_path, [p - 1 for p in pages], output_path)
                outputs_created.append(DocumentOutput(
                    id=uuid.uuid4().hex, job_id=job.id, output_type=OutputType.PDF,
                    storage_key=storage_key, filename=filename,
                    file_size=output_path.stat().st_size, created_at=now_iso(),
                ))
                token.set_stage(stages, "split", 0.2 + 0.6 * (index / total))

            token.set_stage(stages, "package", 0.9)
            if len(outputs_created) > 1:
                output_dir = self.storage.abs_path(f"{OUTPUTS}/{job.id}")
                zip_path = output_dir / "package.zip"
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for output in outputs_created:
                        zf.write(output_dir / output.filename, arcname=output.filename)
                outputs_created.append(DocumentOutput(
                    id=uuid.uuid4().hex, job_id=job.id, output_type=OutputType.ZIP,
                    storage_key=f"{OUTPUTS}/{job.id}/package.zip", filename="package.zip",
                    file_size=zip_path.stat().st_size, created_at=now_iso(),
                ))

            for output in outputs_created:
                self.repository.create_output(output)
            self.repository.update_job(job.id, result_summary={
                "mode": options.mode.value, "file_count": len(groups),
            })
            token.finish_stages(stages)
            self.repository.audit("PDF_SPLIT", job.id, f"{len(groups)} file(s)")

        return target
