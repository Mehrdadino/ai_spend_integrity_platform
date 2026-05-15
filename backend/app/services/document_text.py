"""Extract plain text from stored documents for the worker (step 2a prep).

**Embedded text (free, local):** ``pypdf`` reads the PDF *text layer* — text that was
stored as characters when the PDF was generated (typical e-bills, exports from
billing portals). This is **not** OCR.

**OCR (local / free for v1):** scanned pages are images; ``pypdf`` returns little or no
text. If embedded text is too sparse, we fall back to **Tesseract OCR** for PDFs
and image MIME types.

Tenancy: callers pass an org-scoped ``Document`` row; bytes are loaded from that row's
``bucket`` / ``object_key`` only.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.config import Settings, get_settings
from app.models.document import Document
from app.services.storage import get_document_object_bytes

logger = logging.getLogger(__name__)

_PDF_MIME_PREFIX = "application/pdf"
_IMAGE_MIME_PREFIX = "image/"


class DocumentTextExtractionError(Exception):
    """Bill text could not be obtained (scan, corrupt PDF, empty file)."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class DocumentTextResult:
    """Outcome of reading a stored file; fed to LLM structuring and ``bills.summary``."""

    method: str
    text: str
    page_count: int
    char_count: int
    chars_per_page: float
    has_usable_text: bool
    needs_ocr: bool
    mime_type: str

    def to_summary_dict(self) -> dict[str, Any]:
        """Serializable provenance for ``bills.summary`` (no full bill body)."""
        return {
            "text_extraction_method": self.method,
            "text_page_count": self.page_count,
            "text_char_count": self.char_count,
            "text_chars_per_page": round(self.chars_per_page, 1),
            "text_has_usable_text": self.has_usable_text,
            "text_needs_ocr": self.needs_ocr,
        }


def _collapse_whitespace(text: str) -> str:
    """Normalize PDF copy-paste noise for LLM prompts and char counts."""
    collapsed = re.sub(r"[ \t]+", " ", text)
    collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
    return collapsed.strip()


def _classify_pdf_text(
    *,
    text: str,
    page_count: int,
    mime_type: str,
    min_chars_total: int,
    min_chars_per_page: int,
) -> tuple[bool, bool]:
    """Return ``(has_usable_text, needs_ocr)`` from embedded-text stats."""
    char_count = len(text)
    pages = max(page_count, 1)
    chars_per_page = char_count / pages
    has_usable = char_count >= min_chars_total
    # Low density on a multi-page PDF usually means scan-only pages (images), not a text layer.
    needs_ocr = not has_usable and (
        char_count == 0 or chars_per_page < min_chars_per_page
    )
    if mime_type.startswith(_IMAGE_MIME_PREFIX):
        needs_ocr = True
        has_usable = False
    return has_usable, needs_ocr


def extract_text_from_pdf_bytes(
    body: bytes,
    *,
    mime_type: str = _PDF_MIME_PREFIX,
    min_chars_total: int | None = None,
    min_chars_per_page: int | None = None,
) -> DocumentTextResult:
    """Parse PDF bytes with ``pypdf`` and classify embedded text vs likely scan."""
    settings = get_settings()
    min_total = min_chars_total if min_chars_total is not None else settings.extraction_text_min_chars_total
    min_per_page = (
        min_chars_per_page if min_chars_per_page is not None else settings.extraction_text_min_chars_per_page
    )
    if not body:
        raise DocumentTextExtractionError("Stored object is empty")

    try:
        reader = PdfReader(BytesIO(body), strict=False)
    except PdfReadError as exc:
        raise DocumentTextExtractionError(f"PDF read failed: {exc}") from exc

    page_count = len(reader.pages)
    parts: list[str] = []
    for page in reader.pages:
        try:
            chunk = page.extract_text() or ""
        except Exception as exc:
            logger.warning("document_text: page extract failed: %s", exc)
            chunk = ""
        if chunk.strip():
            parts.append(chunk)

    text = _collapse_whitespace("\n\n".join(parts))
    has_usable, needs_ocr = _classify_pdf_text(
        text=text,
        page_count=page_count,
        mime_type=mime_type,
        min_chars_total=min_total,
        min_chars_per_page=min_per_page,
    )
    char_count = len(text)
    chars_per_page = char_count / max(page_count, 1)

    return DocumentTextResult(
        method="pypdf_embedded",
        text=text,
        page_count=page_count,
        char_count=char_count,
        chars_per_page=chars_per_page,
        has_usable_text=has_usable,
        needs_ocr=needs_ocr,
        mime_type=mime_type,
    )


def _ocr_tesseract_from_image_bytes(
    body: bytes,
    *,
    mime_type: str,
    settings: Settings,
) -> DocumentTextResult:
    """Run local Tesseract OCR over an image-like document (JPEG/PNG/etc.)."""
    if not body:
        raise DocumentTextExtractionError("Image object is empty")

    try:
        from PIL import Image  # type: ignore[import-not-found]
    except Exception as exc:
        raise DocumentTextExtractionError(
            f"OCR not available: Pillow import failed: {exc}",
        ) from exc

    try:
        import pytesseract  # type: ignore[import-not-found]
    except Exception as exc:
        raise DocumentTextExtractionError(
            f"OCR not available: pytesseract import failed: {exc}",
        ) from exc

    try:
        img = Image.open(BytesIO(body))
        img = img.convert("RGB")
        text = pytesseract.image_to_string(img, lang=settings.ocr_tesseract_lang)
    except Exception as exc:
        raise DocumentTextExtractionError(f"Tesseract OCR failed: {exc}") from exc

    text = _collapse_whitespace(text or "")
    char_count = len(text)
    has_usable_text = char_count >= settings.extraction_text_min_chars_total
    if not has_usable_text:
        raise DocumentTextExtractionError(
            "OCR ran but produced no usable text (check scan quality or OCR language).",
        )

    return DocumentTextResult(
        method="tesseract_ocr_image",
        text=text,
        page_count=1,
        char_count=char_count,
        chars_per_page=float(char_count),
        has_usable_text=True,
        needs_ocr=False,
        mime_type=mime_type,
    )


def _ocr_tesseract_from_pdf_bytes(
    body: bytes,
    *,
    mime_type: str,
    settings: Settings,
) -> DocumentTextResult:
    """Run local Tesseract OCR over rendered PDF pages."""
    if not body:
        raise DocumentTextExtractionError("PDF object is empty")
    max_pages = max(1, int(settings.ocr_max_pages))

    try:
        from pdf2image import convert_from_bytes  # type: ignore[import-not-found]
    except Exception as exc:
        raise DocumentTextExtractionError(
            f"OCR not available: pdf2image import failed: {exc}. "
            "Ensure poppler (pdftoppm) is installed on your system for rendering.",
        ) from exc

    try:
        import pytesseract  # type: ignore[import-not-found]
    except Exception as exc:
        raise DocumentTextExtractionError(
            f"OCR not available: pytesseract import failed: {exc}",
        ) from exc

    try:
        pages = convert_from_bytes(
            body,
            dpi=int(settings.ocr_dpi),
            first_page=1,
            last_page=max_pages,
        )
    except Exception as exc:
        raise DocumentTextExtractionError(
            f"PDF render for OCR failed: {exc}. Ensure poppler (pdftoppm) is installed.",
        ) from exc

    text_parts: list[str] = []
    for img in pages:
        try:
            chunk = pytesseract.image_to_string(img, lang=settings.ocr_tesseract_lang)
        except Exception as exc:
            logger.warning("document_text: ocr page failed: %s", exc)
            chunk = ""
        if chunk and chunk.strip():
            text_parts.append(chunk)

    text = _collapse_whitespace("\n\n".join(text_parts))
    char_count = len(text)
    has_usable_text = char_count >= settings.extraction_text_min_chars_total
    if not has_usable_text:
        raise DocumentTextExtractionError(
            "OCR ran but produced no usable text (check scan quality or OCR language).",
        )

    page_count = len(pages)
    return DocumentTextResult(
        method="tesseract_ocr_pdf",
        text=text,
        page_count=page_count,
        char_count=char_count,
        chars_per_page=char_count / max(page_count, 1),
        has_usable_text=True,
        needs_ocr=False,
        mime_type=mime_type,
    )


def extract_text_for_document(
    document: Document,
    *,
    settings: Settings | None = None,
) -> DocumentTextResult | None:
    """Load object bytes from S3 and extract text when MIME is PDF; ``None`` if skipped MIME.

    Raises ``DocumentTextExtractionError`` on corrupt PDF/invalid image/empty document
    or when OCR runs but produces no usable text.
    """
    settings = settings or get_settings()
    mime = (document.mime_type or "").strip().lower()

    if mime.startswith(_IMAGE_MIME_PREFIX):
        body = get_document_object_bytes(bucket=document.bucket, key=document.object_key)
        return _ocr_tesseract_from_image_bytes(body, mime_type=mime, settings=settings)

    if not mime.startswith(_PDF_MIME_PREFIX):
        logger.info(
            "document_text: skip mime=%s document=%s (only PDF embedded-text supported)",
            mime,
            document.id,
        )
        return None

    body = get_document_object_bytes(bucket=document.bucket, key=document.object_key)
    result = extract_text_from_pdf_bytes(
        body,
        mime_type=mime,
        min_chars_total=settings.extraction_text_min_chars_total,
        min_chars_per_page=settings.extraction_text_min_chars_per_page,
    )
    if result.needs_ocr and settings.ocr_provider == "tesseract":
        return _ocr_tesseract_from_pdf_bytes(
            body,
            mime_type=mime,
            settings=settings,
        )
    return result


def truncate_text_for_llm(text: str, *, max_chars: int | None = None) -> str:
    """Bound prompt size; keep head + tail so totals at end of long bills may survive."""
    settings = get_settings()
    limit = max_chars if max_chars is not None else settings.extraction_llm_max_document_chars
    if len(text) <= limit:
        return text
    marker = "\n\n[... truncated for model context ...]\n\n"
    budget = limit - len(marker)
    if budget < 20:
        return text[:limit]
    head = int(budget * 0.7)
    tail = budget - head
    return f"{text[:head]}{marker}{text[-tail:]}"
