"""Page thumbnails, generated on demand and cached (sections 13, 51-52).

Never renders more than one page at a time - the frontend asks for one
thumbnail per visible grid cell (virtualized), so an 8,000-page document
never causes 8,000 renders up front.
"""

from __future__ import annotations

from ..config import DocumentSettings
from ..exceptions import DocumentError, DocumentNotFoundError, PageRangeError
from ..pdf_engine import open_pdf
from ..repository import DocumentRepository
from ..storage import THUMBNAILS, StorageProvider


class PreviewService:
    def __init__(self, storage: StorageProvider, repository: DocumentRepository, settings: DocumentSettings):
        self.storage = storage
        self.repository = repository
        self.settings = settings

    def get_thumbnail(self, document_id: str, page_index: int, max_dim: int = 320) -> bytes:
        document = self.repository.get_document(document_id)
        if document is None:
            raise DocumentNotFoundError(f"Document '{document_id}' was not found.")
        if document.mime_type != "application/pdf":
            raise DocumentError("Thumbnails are only available for PDF documents.")

        thumb_key = f"{THUMBNAILS}/{document_id}/page-{page_index}-{max_dim}.png"
        if self.storage.exists(thumb_key):
            with self.storage.open_read(thumb_key) as fh:
                return fh.read()

        with open_pdf(self.storage.abs_path(document.storage_key)) as pdf:
            if page_index < 0 or page_index >= pdf.page_count:
                raise PageRangeError(
                    f"Page {page_index + 1} does not exist (document has {pdf.page_count} pages)."
                )
            data = pdf.render_thumbnail(page_index, max_dim)

        self.storage.write_bytes(THUMBNAILS, document_id, f"page-{page_index}-{max_dim}.png", data)
        return data
