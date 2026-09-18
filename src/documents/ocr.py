"""Interchangeable OCR backend (section 11).

The pipeline decides *whether* OCR is needed (PDFDocument.has_extractable_text);
this module only decides *how* to run it, behind `OCRProvider`, so the
concrete engine (local Tesseract today; a hosted or AI-based provider
later) is never hard-wired into the conversion pipeline.

Like ffmpeg for the YouTube/Whisper path, Tesseract is an external
binary this module does not bundle: if it is missing, OCR raises a
clear, specific error instead of a stack trace, and the rest of the
conversion still completes (pages that needed OCR are marked
uncertain rather than silently dropped).
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from io import BytesIO

from .exceptions import OCRUnavailableError


class OCRProvider(ABC):
    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def recognize(self, image_bytes: bytes, language: str = "auto") -> str:
        """Return the recognized text for one rendered page image."""


class NullOCRProvider(OCRProvider):
    """Used when OCR is disabled or requested for a page that turns out
    to already have a text layer - never invoked for actual recognition."""

    def is_available(self) -> bool:
        return True

    def recognize(self, image_bytes: bytes, language: str = "auto") -> str:
        return ""


_TESSERACT_LANG_MAP = {
    "auto": None,
    "en": "eng",
    "fr": "fra",
    "es": "spa",
    "de": "deu",
    "it": "ita",
    "pt": "por",
}


class TesseractOCRProvider(OCRProvider):
    def is_available(self) -> bool:
        return shutil.which("tesseract") is not None

    def recognize(self, image_bytes: bytes, language: str = "auto") -> str:
        if not self.is_available():
            raise OCRUnavailableError(
                "OCR was requested, but the Tesseract binary is not installed or not on PATH. "
                "Install it (e.g. `winget install --id UB-Mannheim.TesseractOCR`) and retry, "
                "or disable OCR for this conversion."
            )
        import pytesseract
        from PIL import Image

        image = Image.open(BytesIO(image_bytes))
        lang = _TESSERACT_LANG_MAP.get(language, "eng+fra") or "eng+fra"
        try:
            return pytesseract.image_to_string(image, lang=lang)
        except pytesseract.TesseractError:
            # Requested language pack not installed locally; fall back to
            # English rather than failing the whole conversion.
            return pytesseract.image_to_string(image)


def get_ocr_provider(mode: str) -> OCRProvider:
    """`mode` is one of "never" (NullOCRProvider) or "auto"/"always"
    (TesseractOCRProvider, the only real engine wired up today)."""
    if mode == "never":
        return NullOCRProvider()
    return TesseractOCRProvider()
