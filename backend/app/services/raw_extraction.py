"""Persist raw LLM JSON for a document (step 2a); currently a deterministic stub.

Payloads pass strict Pydantic validation (step **2b**) before JSONB insert; there is
no repair path—invalid data raises and the worker marks ``failed``.

The worker calls this after marking ``received`` so extraction failures can be
distinguished from ingestion failures via ``documents.processing_status`` /
``processing_error``.
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
    """
    settings = get_settings()
    model_id = settings.raw_extraction_stub_model_id
    candidate: dict[str, Any] = {
        "stub": True,
        "message": "No frontier LLM wired yet; 2a persistence only.",
        "document_id": str(document.id),
        "mime_type": document.mime_type,
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
