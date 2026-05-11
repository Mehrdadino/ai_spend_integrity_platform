"""RQ job handlers for the document ingestion pipeline (step 1d onward).

``process_document_pipeline`` is intentionally small: acknowledge bytes are
stored and hand off to future extraction (step 2). Idempotent if the job is
retried or duplicated.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.db.session import get_session_factory
from app.models.document import Document

logger = logging.getLogger(__name__)

# Rows created before 1d used ``pending``; new rows use ``queued`` after finalize.
_STATUSES_READY_FOR_WORKER = frozenset({"queued", "pending"})

PROCESSING_RECEIVED = "received"


def process_document_pipeline(document_id: str) -> None:
    """Mark document as worker-acknowledged (``received``). Safe to retry.

    Opens its own DB session because RQ runs outside the FastAPI request scope.
    """
    oid = uuid.UUID(document_id)
    factory = get_session_factory()
    session: Session = factory()
    try:
        doc = session.get(Document, oid)
        if doc is None:
            logger.warning("document_jobs: document not found id=%s", document_id)
            return
        if doc.processing_status not in _STATUSES_READY_FOR_WORKER:
            logger.info(
                "document_jobs: skip id=%s status=%s",
                document_id,
                doc.processing_status,
            )
            return
        doc.processing_status = PROCESSING_RECEIVED
        session.commit()
        logger.info("document_jobs: id=%s -> %s", document_id, PROCESSING_RECEIVED)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
