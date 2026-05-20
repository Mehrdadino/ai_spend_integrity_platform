"""RQ job handlers for the document ingestion pipeline (1d → 2a → 2b → 2c → 2d).

Loads the PDF from S3, extracts **embedded text** (``pypdf``), optionally structures via
LLM, **Pydantic-validates** (2b), inserts JSONB, assesses utility-bill validity, then
upserts normalized bills (2c/2d) only when supported.

``failed`` = technical pipeline error. ``unsupported`` = processed file is not treated
as a utility bill (see ``document_validity``).

After a successful bill upsert, **§3e** enqueues ``comparison_queue`` so anomalies are
refreshed without calling ``GET …/bill/comparison`` in the browser.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.document_processing import (
    PROCESSING_EXTRACTED,
    PROCESSING_FAILED,
    PROCESSING_RECEIVED,
    PROCESSING_UNSUPPORTED,
)
from app.db.session import get_session_factory
from app.models.bill import Bill
from app.models.document import Document
from app.services.bill_sync import upsert_bill_for_document
from app.services.comparison_queue import enqueue_document_comparison_backfill_safe
from app.services.document_validity import assess_document_validity
from app.services.normalization.from_extraction import build_normalized_bundle
from app.services.raw_extraction import persist_raw_extraction_for_document

logger = logging.getLogger(__name__)

# ``received`` = worker started but may have crashed (RQ timeout / SIGABRT); allow resume.
_STATUSES_READY_FOR_WORKER = frozenset({"queued", "pending", "received"})
_MAX_ERROR_LEN = 8000


def _truncate_error(message: str) -> str:
    """Bound ``processing_error`` size (Postgres TEXT is still worth capping for UI)."""
    if len(message) <= _MAX_ERROR_LEN:
        return message
    return message[: _MAX_ERROR_LEN - 24] + "…(error truncated)"


def _mark_unsupported(
    session: Session,
    *,
    document: Document,
    reason_code: str,
    user_message: str,
) -> None:
    """Drop any prior bill row and mark the document unsupported (not ``failed``)."""
    existing = session.scalar(select(Bill).where(Bill.document_id == document.id))
    if existing is not None:
        session.delete(existing)
        session.flush()
    document.processing_status = PROCESSING_UNSUPPORTED
    document.unsupported_reason_code = reason_code
    document.unsupported_reason = user_message
    document.processing_error = None


def process_document_pipeline(document_id: str) -> None:
    """Run received → extraction → validity → optional 2d; persist terminal status.

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
        if doc.processing_status == PROCESSING_UNSUPPORTED:
            logger.info("document_jobs: already unsupported id=%s", document_id)
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
            doc.unsupported_reason = None
            doc.unsupported_reason_code = None
            if doc.processing_status != PROCESSING_RECEIVED:
                doc.processing_status = PROCESSING_RECEIVED
                session.flush()
            raw_row, provenance = persist_raw_extraction_for_document(session, document=doc)
            bundle = build_normalized_bundle(document=doc, raw_row=raw_row)
            assessment = assess_document_validity(
                document=doc,
                bundle=bundle,
                provenance=provenance,
            )
            if not assessment.is_utility_bill:
                _mark_unsupported(
                    session,
                    document=doc,
                    reason_code=assessment.reason_code or "unsupported",
                    user_message=assessment.user_message or "Not recognized as a utility bill.",
                )
                session.commit()
                logger.info(
                    "document_jobs: id=%s -> %s reason=%s",
                    document_id,
                    PROCESSING_UNSUPPORTED,
                    assessment.reason_code,
                )
                return

            upsert_bill_for_document(
                session,
                document=doc,
                raw_extraction=raw_row,
                summary_extra=provenance,
            )
            doc.processing_status = PROCESSING_EXTRACTED
            doc.unsupported_reason = None
            doc.unsupported_reason_code = None
            session.commit()
            logger.info("document_jobs: id=%s -> %s", document_id, PROCESSING_EXTRACTED)
            enqueue_document_comparison_backfill_safe(oid)
        except Exception as exc:
            session.rollback()
            doc_failed = session.get(Document, oid)
            if doc_failed is None:
                logger.exception("document_jobs: document missing after failure id=%s", document_id)
                return
            doc_failed.processing_status = PROCESSING_FAILED
            doc_failed.processing_error = _truncate_error(f"{type(exc).__name__}: {exc}")
            doc_failed.unsupported_reason = None
            doc_failed.unsupported_reason_code = None
            try:
                session.commit()
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
