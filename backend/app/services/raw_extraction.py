"""Persist raw LLM JSON for a document (step 2a); currently a deterministic stub.

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
from app.models.document import Document
from app.models.document_raw_extraction import DocumentRawExtraction

logger = logging.getLogger(__name__)

# Bump when the stub payload shape changes (auditing / replays).
STUB_EXTRACTION_VERSION = "stub-v1"


def persist_stub_raw_extraction(session: Session, *, document: Document) -> DocumentRawExtraction:
    """Insert one JSONB row and leave ``document`` on ``extracted`` for the happy path.

    Replace with a real LLM call later; keep the insert + status transition in one
    transaction with the worker's outer ``commit``.
    """
    settings = get_settings()
    model_id = settings.raw_extraction_stub_model_id
    payload: dict[str, Any] = {
        "stub": True,
        "message": "No frontier LLM wired yet; 2a persistence only.",
        "document_id": str(document.id),
        "mime_type": document.mime_type,
    }
    row = DocumentRawExtraction(
        id=uuid.uuid4(),
        document_id=document.id,
        raw_payload=payload,
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
