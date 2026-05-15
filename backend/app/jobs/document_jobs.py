"""RQ job handlers for the document ingestion pipeline (1d → 2a → 2b → 2c → 2d).

Loads the PDF from S3, extracts **embedded text** (``pypdf``), optionally structures via
LLM, **Pydantic-validates** (2b), inserts JSONB, then upserts normalized bills (2c/2d).
Scanned PDFs with no text layer fail with a clear ``processing_error`` (OCR TBD).
Validation failures raise ``ExtractionPayloadValidationError``; the worker maps any
exception to ``failed`` + ``processing_error`` (no repair).

After a successful bill upsert, **§3e** enqueues ``comparison_queue`` so anomalies are
refreshed without calling ``GET …/bill/comparison`` in the browser.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.db.session import get_session_factory
from app.models.document import Document
from app.services.bill_sync import upsert_bill_for_document
from app.services.comparison_queue import enqueue_document_comparison_backfill_safe
from app.services.raw_extraction import persist_raw_extraction_for_document

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
            raw_row, provenance = persist_raw_extraction_for_document(session, document=doc)
            upsert_bill_for_document(
                session,
                document=doc,
                raw_extraction=raw_row,
                summary_extra=provenance,
            )
            session.commit()
            logger.info("document_jobs: id=%s -> %s", document_id, PROCESSING_EXTRACTED)
            # §3e: persist anomalies without requiring GET /bill/comparison from the UI.
            enqueue_document_comparison_backfill_safe(oid)
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
                # ``processing_error`` is nullable; slice only when a string is present.
                err_snip = (doc_failed.processing_error or "")[:200]
                logger.warning(
                    "document_jobs: id=%s -> %s err=%s",
                    document_id,
                    PROCESSING_FAILED,
                    err_snip,
                )
            except Exception:
                session.rollback()
                logger.exception("document_jobs: could not persist failure id=%s", document_id)
    finally:
        session.close()
