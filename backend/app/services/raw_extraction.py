"""Persist raw extraction JSON for a document (2a) then ``bill_sync`` consumes it (2d).

Pipeline: load bytes from S3 → **embedded PDF text** (``pypdf``) → optional
**Tesseract OCR** if embedded text is too sparse → optional **LLM**
structuring → strict Pydantic (**2b**) → JSONB insert.

When ``Settings.extraction_llm_api_key`` is empty, a **deterministic** sample payload
is still used for dev/CI (see ``structured_via`` in returned provenance).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants.extraction import GENERIC_BILL_EXTRACTION_VERSION
from app.models.document import Document
from app.models.document_raw_extraction import DocumentRawExtraction
from app.services.document_text import (
    DocumentTextExtractionError,
    DocumentTextResult,
    extract_text_for_document,
)
from app.services.extraction_llm import safe_llm_generic_bill_dict
from app.services.extraction_validate import validate_raw_extraction_payload

logger = logging.getLogger(__name__)


def build_deterministic_generic_bill_dict(document: Document) -> dict[str, Any]:
    """Seed ``generic-bill-v1`` JSON without LLM (dev/CI when no API key or LLM failure)."""
    return {
        "document_id": str(document.id),
        "spend_domain": "utility",
        "spend_kind": "electricity",
        "issuer_name": None,
        "currency": "USD",
        "lines": [
            {
                "raw_label": "Electricity delivery (sample)",
                "amount": 142.5,
                "currency": "USD",
                "quantity": 950.0,
                "quantity_unit": "kwh",
                "service_hint": "electric",
            },
        ],
    }


def _provenance_base(text_result: DocumentTextResult | None) -> dict[str, Any]:
    """Merge text-extraction stats for ``bills.summary`` (no full bill body)."""
    if text_result is None:
        return {"text_extraction_method": "skipped_unsupported_mime"}
    return dict(text_result.to_summary_dict())


def persist_raw_extraction_for_document(
    session: Session,
    *,
    document: Document,
) -> tuple[DocumentRawExtraction, dict[str, Any]]:
    """Validate extraction JSON (2b), insert ``document_raw_extractions``, set ``extracted``.

    Returns the new row and a provenance dict for ``bill_sync`` summary merge.
    """
    settings = get_settings()
    text_result: DocumentTextResult | None = None
    try:
        text_result = extract_text_for_document(document, settings=settings)
    except DocumentTextExtractionError:
        raise
    except Exception as exc:
        raise DocumentTextExtractionError(f"Could not read document bytes: {exc}") from exc

    provenance = _provenance_base(text_result)

    bill_text = text_result.text if text_result and text_result.has_usable_text else None
    candidate: dict[str, Any]
    model_id: str
    has_llm_key = bool((settings.extraction_llm_api_key or "").strip())

    if has_llm_key:
        llm_out, llm_error = safe_llm_generic_bill_dict(
            document=document,
            settings=settings,
            document_text=bill_text,
        )
        if llm_out is not None:
            candidate = llm_out
            model_id = settings.extraction_llm_model
            provenance["structured_via"] = "llm"
        else:
            candidate = build_deterministic_generic_bill_dict(document)
            model_id = settings.raw_extraction_stub_model_id
            provenance["structured_via"] = "deterministic_fallback"
            if llm_error:
                provenance["structured_error"] = llm_error
            provenance["structured_note"] = (
                "Line items below are a dev sample because LLM structuring failed. "
                "Fix EXTRACTION_LLM_* settings and reprocess."
            )
    else:
        if bill_text:
            provenance["structured_via"] = "deterministic_stub"
            provenance["structured_note"] = (
                "Set EXTRACTION_LLM_API_KEY to structure line items from extracted PDF text."
            )
        else:
            provenance["structured_via"] = "deterministic_stub"
        candidate = build_deterministic_generic_bill_dict(document)
        model_id = settings.raw_extraction_stub_model_id

    raw_payload = validate_raw_extraction_payload(
        candidate,
        extraction_version=GENERIC_BILL_EXTRACTION_VERSION,
        expected_document_id=document.id,
    )
    row = DocumentRawExtraction(
        id=uuid.uuid4(),
        document_id=document.id,
        raw_payload=raw_payload,
        model_id=model_id,
        extraction_version=GENERIC_BILL_EXTRACTION_VERSION,
    )
    session.add(row)
    # Final status (``extracted`` vs ``unsupported`` vs ``failed``) is set by ``document_jobs``.
    session.flush()
    logger.info(
        "raw_extraction: stored id=%s document=%s version=%s model_id=%s chars=%s via=%s",
        row.id,
        document.id,
        GENERIC_BILL_EXTRACTION_VERSION,
        model_id,
        text_result.char_count if text_result else 0,
        provenance.get("structured_via"),
    )
    return row, provenance


def persist_stub_raw_extraction(session: Session, *, document: Document) -> DocumentRawExtraction:
    """Backward-compatible name for tests / imports; delegates to ``generic-bill-v1``."""
    row, _ = persist_raw_extraction_for_document(session, document=document)
    return row
