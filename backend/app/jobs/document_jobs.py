"""RQ job handlers for the document ingestion pipeline (1d → 2a → 2b).

After storage ack, stub extraction JSON is **Pydantic-validated** (2b) before JSONB
insert. Validation failures raise ``ExtractionPayloadValidationError``; the worker
maps any exception to ``failed`` + ``processing_error`` (no repair). Idempotent for
already-``extracted`` rows (no-op).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.db.session import get_session_factory
from app.models.document import Document
from app.services.raw_extraction import persist_stub_raw_extraction

logger = logging.getLogger(__name__)

_STATUSES_READY_FOR_WORKER = frozenset({"queued", "pending"})
PROCESSING_RECEIVED = "received"
PROCESSING_EXTRACTED = "extracted"
PROCESSING_FAILED = "failed"
_MAX_ERROR_LEN = 8000


def _truncate_error(message: str) -> str:
    """Bound ``processing_error`` size (Postgres TEXT is still worth capping for UI)."""
    if len(message) <= _MAX_ERROR_LEN:
        return message
    return message[: _MAX_ERROR_LEN - 24] + "…(error truncated)"


def process_document_pipeline(document_id: str) -> None:
    """Run received → validated stub raw extraction (2a/2b); persist ``failed`` + error on exception.

    Uses its own DB session because RQ runs outside the FastAPI request scope.
    """
    oid = uuid.UUID(document_id)
    factory = get_session_factory()
    session: Session = factory()
    try:
        doc = session.get(Document, oid)
        if doc is None:
            logger.warning("document_jobs: document not found id=%s", document_id)
            return
        if doc.processing_status == PROCESSING_EXTRACTED:
            logger.info("document_jobs: already extracted id=%s", document_id)
            return
        if doc.processing_status not in _STATUSES_READY_FOR_WORKER:
            logger.info(
                "document_jobs: skip id=%s status=%s",
                document_id,
                doc.processing_status,
            )
            return

        try:
            doc.processing_error = None
            doc.processing_status = PROCESSING_RECEIVED
            session.flush()
            persist_stub_raw_extraction(session, document=doc)
            session.commit()
            logger.info("document_jobs: id=%s -> %s", document_id, PROCESSING_EXTRACTED)
        except Exception as exc:
            session.rollback()
            doc_failed = session.get(Document, oid)
            if doc_failed is None:
                logger.exception("document_jobs: document missing after failure id=%s", document_id)
                return
            doc_failed.processing_status = PROCESSING_FAILED
            doc_failed.processing_error = _truncate_error(f"{type(exc).__name__}: {exc}")
            try:
                session.commit()
                logger.warning(
                    "document_jobs: id=%s -> %s err=%s",
                    document_id,
                    PROCESSING_FAILED,
                    doc_failed.processing_error[:200],
                )
            except Exception:
                session.rollback()
                logger.exception("document_jobs: could not persist failure id=%s", document_id)
    finally:
        session.close()
