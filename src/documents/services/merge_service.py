"""PDF merge, with optional per-file page selection (sections 16-17)."""

from __future__ import annotations

import uuid

from ..config import DocumentSettings
from ..exceptions import DocumentNotFoundError, ResourceLimitError
from ..job_queue import CancelToken, JobTarget
from ..models import DocumentJob, DocumentOutput, JobOperation, MergeOptions, OutputType, PipelineStage
from ..pdf_engine import merge_pdfs
from ..repository import DocumentRepository, now_iso
from ..storage import OUTPUTS, StorageProvider
from ..validation import parse_page_ranges, sanitize_display_name

STAGE_DEFS = [
    ("validate", "Validating documents"),
    ("merge", "Merging pages"),
    ("package", "Packaging output"),
]


class MergeService:
    def __init__(self, storage: StorageProvider, repository: DocumentRepository, settings: DocumentSettings):
        self.storage = storage
        self.repository = repository
        self.settings = settings

    def create_job(self, options: MergeOptions) -> DocumentJob:
        if not options.inputs:
            raise ResourceLimitError("Select at least one PDF to merge.")
        if len(options.inputs) > self.settings.max_files_per_merge:
            raise ResourceLimitError(
                f"A merge can combine at most {self.settings.max_files_per_merge} files at once."
            )
        for merge_input in options.inputs:
            document = self.repository.get_document(merge_input.document_id)
            if document is None:
                raise DocumentNotFoundError(f"Document '{merge_input.document_id}' was not found.")
            if merge_input.page_ranges:
                parse_page_ranges(merge_input.page_ranges, document.page_count or 0)

        stages = [PipelineStage(key=k, label=label) for k, label in STAGE_DEFS]
        job = DocumentJob(
            id=uuid.uuid4().hex,
            operation=JobOperation.MERGE,
            stages=stages,
            input_document_ids=[i.document_id for i in options.inputs],
            options=options.model_dump(),
            created_at=now_iso(),
        )
        self.repository.create_job(job)
        self.repository.audit("PDF_MERGE_QUEUED", job.id, f"{len(options.inputs)} file(s)")
        return job

    def build_target(self, job: DocumentJob) -> JobTarget:
        options = MergeOptions(**job.options)

        def target(token: CancelToken) -> None:
            stages = [PipelineStage(**s.model_dump()) for s in job.stages]
            token.set_stage(stages, "validate", 0.05)

            sources = []
            for merge_input in options.inputs:
                token.check()
                document = self.repository.get_document(merge_input.document_id)
                if document is None:
                    raise DocumentNotFoundError(f"Document '{merge_input.document_id}' was not found.")
                path = self.storage.abs_path(document.storage_key)
                indices = None
                if merge_input.page_ranges:
                    pages = parse_page_ranges(merge_input.page_ranges, document.page_count or 0)
                    indices = [p - 1 for p in pages]
                sources.append((path, indices))

            token.set_stage(stages, "merge", 0.4)
            token.check()

            output_name = sanitize_display_name(options.output_name or "merged-document.pdf")
            if not output_name.lower().endswith(".pdf"):
                output_name += ".pdf"
            storage_key, output_path = self.storage.reserve_path(OUTPUTS, job.id, output_name)
            page_count = merge_pdfs(sources, output_path)

            token.set_stage(stages, "package", 0.9)
            output = DocumentOutput(
                id=uuid.uuid4().hex, job_id=job.id, output_type=OutputType.PDF,
                storage_key=storage_key, filename=output_name,
                file_size=output_path.stat().st_size, created_at=now_iso(),
            )
            self.repository.create_output(output)
            self.repository.update_job(job.id, result_summary={
                "output_name": output_name, "page_count": page_count, "source_count": len(sources),
            })
            token.finish_stages(stages)
            self.repository.audit("PDF_MERGED", job.id, output_name)

        return target
