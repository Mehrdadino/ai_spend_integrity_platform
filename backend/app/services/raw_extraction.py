"""Persist raw extraction JSON for a document (2a) then ``bill_sync`` consumes it (2d).

New pipeline rows use ``generic-bill-v1`` (strict Pydantic in **2b**). When
``Settings.extraction_llm_api_key`` is set, the worker first asks an OpenAI-compatible
Chat Completions endpoint; on any failure it falls back to a **deterministic** payload
so dev and CI stay green without network.

``stub-v1`` remains valid for **reading** older JSONB rows; new inserts use
``generic-bill-v1`` only.
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
from app.services.extraction_llm import safe_llm_generic_bill_dict
from app.services.extraction_validate import validate_raw_extraction_payload

logger = logging.getLogger(__name__)


def build_deterministic_generic_bill_dict(document: Document) -> dict[str, Any]:
    """Seed ``generic-bill-v1`` JSON without LLM (same shape as previous stub sample)."""
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


def persist_raw_extraction_for_document(session: Session, *, document: Document) -> DocumentRawExtraction:
    """Validate extraction JSON (2b), insert ``document_raw_extractions``, set ``extracted``.

    Returns the new row so the worker can set ``bills.raw_extraction_id``.
    """
    settings = get_settings()
    candidate: dict[str, Any]
    model_id: str

    if (settings.extraction_llm_api_key or "").strip():
        llm_out = safe_llm_generic_bill_dict(document=document, settings=settings)
        if llm_out is not None:
            candidate = llm_out
            model_id = settings.extraction_llm_model
        else:
            candidate = build_deterministic_generic_bill_dict(document)
            model_id = settings.raw_extraction_stub_model_id
    else:
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
    document.processing_status = "extracted"
    session.flush()
    logger.info(
        "raw_extraction: stored id=%s document=%s version=%s model_id=%s",
        row.id,
        document.id,
        GENERIC_BILL_EXTRACTION_VERSION,
        model_id,
    )
    return row


def persist_stub_raw_extraction(session: Session, *, document: Document) -> DocumentRawExtraction:
    """Backward-compatible name for tests / imports; delegates to ``generic-bill-v1``."""
    return persist_raw_extraction_for_document(session, document=document)
