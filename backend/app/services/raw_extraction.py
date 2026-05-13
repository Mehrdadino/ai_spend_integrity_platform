"""Persist raw LLM JSON for a document (step 2a); currently a deterministic stub.

Payloads pass strict Pydantic validation (step **2b**) before JSONB insert; there is
no repair path—invalid data raises and the worker marks ``failed``.

Optional ``draft_lines`` on ``stub-v1`` feed **2c** normalization and **2d** bill
rows via ``bill_sync`` in the worker after this function returns.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants.extraction import STUB_EXTRACTION_VERSION
from app.models.document import Document
from app.models.document_raw_extraction import DocumentRawExtraction
from app.services.extraction_validate import validate_raw_extraction_payload

logger = logging.getLogger(__name__)


def persist_stub_raw_extraction(session: Session, *, document: Document) -> DocumentRawExtraction:
    """Build stub dict, **validate** (2b), insert JSONB row, set ``extracted``.

    ``raw_payload`` stores the validated ``model_dump(mode="json")`` snapshot only.
    Returns the new row so callers (worker ``bill_sync``) can attach ``bills.raw_extraction_id``.
    """
    settings = get_settings()
    model_id = settings.raw_extraction_stub_model_id
    candidate: dict[str, Any] = {
        "stub": True,
        "message": "No frontier LLM wired yet; 2a persistence + optional draft lines for 2c/2d.",
        "document_id": str(document.id),
        "mime_type": document.mime_type,
        "spend_domain": "utility",
        "spend_kind": "electricity",
        "draft_lines": [
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
    raw_payload = validate_raw_extraction_payload(
        candidate,
        extraction_version=STUB_EXTRACTION_VERSION,
        expected_document_id=document.id,
    )
    row = DocumentRawExtraction(
        id=uuid.uuid4(),
        document_id=document.id,
        raw_payload=raw_payload,
        model_id=model_id,
        extraction_version=STUB_EXTRACTION_VERSION,
    )
    session.add(row)
    document.processing_status = "extracted"
    session.flush()
    logger.info(
        "raw_extraction: stored stub id=%s document=%s version=%s",
        row.id,
        document.id,
        STUB_EXTRACTION_VERSION,
    )
    return row
