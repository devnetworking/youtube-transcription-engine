"""Upload ingestion and the file library (sections 4, 24, 25, 29, 31, 35)."""

from __future__ import annotations

import uuid
from typing import BinaryIO, Optional

from ..config import DocumentSettings
from ..exceptions import DocumentNotFoundError, InvalidUploadError, ResourceLimitError
from ..models import Document, DocumentStatus
from ..pdf_engine import open_pdf
from ..repository import DocumentRepository, now_iso
from ..storage import OUTPUTS, UPLOADS, StorageProvider
from ..validation import sanitize_display_name, validate_extension, validate_pdf_header


class DocumentService:
    def __init__(self, storage: StorageProvider, repository: DocumentRepository, settings: DocumentSettings):
        self.storage = storage
        self.repository = repository
        self.settings = settings

    def ingest_upload(self, stream: BinaryIO, declared_filename: str) -> Document:
        display_name = sanitize_display_name(declared_filename)
        validate_extension(display_name, self.settings.allowed_upload_extensions)

        document_id = uuid.uuid4().hex
        max_bytes = self.settings.max_upload_size_mb * 1024 * 1024
        storage_key, size_bytes, checksum = self.storage.save_stream(
            UPLOADS, document_id, "original.pdf", stream, max_size_bytes=max_bytes
        )

        try:
            with self.storage.open_read(storage_key) as fh:
                header = fh.read(5)
            validate_pdf_header(header)

            existing = self.repository.find_by_checksum(checksum)
            if existing is not None:
                # Same bytes already stored (section 35): drop the fresh
                # copy and hand back the existing document instead of
                # doubling storage for an identical re-upload.
                self.storage.delete_entity(UPLOADS, document_id)
                self.repository.audit("DOCUMENT_UPLOADED", existing.id, "deduplicated")
                return existing

            with open_pdf(self.storage.abs_path(storage_key)) as pdf:
                page_count = pdf.page_count

            if page_count > self.settings.max_pages_per_document:
                raise ResourceLimitError(
                    f"This document has {page_count} pages, over the configured limit of "
                    f"{self.settings.max_pages_per_document}."
                )
        except (InvalidUploadError, ResourceLimitError):
            self.storage.delete_entity(UPLOADS, document_id)
            raise
        except Exception as exc:
            self.storage.delete_entity(UPLOADS, document_id)
            raise InvalidUploadError(
                "The PDF appears to be corrupted and could not be processed."
            ) from exc

        document = Document(
            id=document_id,
            original_name=display_name,
            storage_key=storage_key,
            mime_type="application/pdf",
            file_size=size_bytes,
            page_count=page_count,
            checksum_sha256=checksum,
            status=DocumentStatus.READY,
            created_at=now_iso(),
        )
        self.repository.create_document(document)
        self.repository.audit("DOCUMENT_UPLOADED", document.id, display_name)
        return document

    def get(self, document_id: str) -> Document:
        document = self.repository.get_document(document_id)
        if document is None or document.status == DocumentStatus.DELETED:
            raise DocumentNotFoundError(f"Document '{document_id}' was not found.")
        return document

    def list(self, search: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[Document]:
        return self.repository.list_documents(search=search, limit=limit, offset=offset)

    def count(self) -> int:
        return self.repository.count_documents()

    def related_jobs(self, document: Document) -> list:
        """Jobs relevant to this document's History/Derived files tabs:
        jobs that took it as *input* (e.g. a PDF that was converted or
        split), plus, for a generated document (section 34) such as a
        YouTube transcript, the one job that *produced* it - it has no
        "input" job since nothing was uploaded for it."""
        jobs = self.repository.jobs_for_document(document.id)
        if document.source_job_id and not any(j.id == document.source_job_id for j in jobs):
            source_job = self.repository.get_job(document.source_job_id)
            if source_job:
                jobs = [source_job, *jobs]
        return jobs

    def derived_outputs(self, document_id: str):
        document = self.get(document_id)
        jobs = self.related_jobs(document)
        outputs = []
        for job in jobs:
            outputs.extend(self.repository.list_outputs(job.id))
        return jobs, outputs

    def rename(self, document_id: str, new_name: str) -> Document:
        self.get(document_id)  # raises DocumentNotFoundError if missing/deleted
        display_name = sanitize_display_name(new_name)
        self.repository.rename_document(document_id, display_name)
        self.repository.audit("DOCUMENT_RENAMED", document_id, display_name)
        return self.get(document_id)

    def delete(self, document_id: str) -> None:
        document = self.get(document_id)
        jobs = self.related_jobs(document)
        for job in jobs:
            self.storage.delete_entity(OUTPUTS, job.id)
        self.storage.delete_entity(UPLOADS, document_id)
        self.repository.soft_delete_document(document_id)
        self.repository.audit("DOCUMENT_DELETED", document_id, document.original_name)
