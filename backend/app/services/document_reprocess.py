"""Re-run the ingestion worker for a document (1d → 2a–2d).

Resets ``processing_status`` to ``queued``, clears ``processing_error``, and the API
enqueues ``process_document_pipeline`` after DB commit (same pattern as
``complete_presigned_upload``).

Allowed states include **``queued``** and **``pending``** so operators can recover after an
RQ work-horse crash (e.g. SIGABRT on macOS) where the row never advanced but Redis no
longer holds a pending job. Slight risk of duplicate jobs if a real worker is still
running; acceptable for dev; tighten with auth / job checks in production.

Tenancy: callers must load the ``Document`` via ``organization_id`` + ``document_id``.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.document import Document
from app.repositories.documents import get_document_for_organization

# Terminal / stuck / retryable pipeline states (includes ``queued`` for crash recovery).
_STATUSES_REPROCESSABLE = frozenset(
    {"extracted", "failed", "received", "queued", "pending"},
)


class ReprocessDocumentBadRequest(Exception):
    """Upload not finalized, or status is not recognized for reprocess."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def prepare_document_for_pipeline_reprocess(session: Session, *, document: Document) -> None:
    """Mutate ``document`` to ``queued`` and clear errors if reprocess is allowed.

    Flushes the session so the row is visible to the worker after commit. Raises
    ``ReprocessDocumentBadRequest`` on invalid state. Does not commit or enqueue
    (HTTP layer handles those).
    """
    if document.sha256 is None or document.byte_size is None:
        raise ReprocessDocumentBadRequest(
            "Document has no stored object yet; finish the presigned upload first.",
        )
    status = document.processing_status
    if status == "awaiting_object":
        raise ReprocessDocumentBadRequest(
            "Upload is not finalized (awaiting_object); complete the PUT flow instead.",
        )
    if status not in _STATUSES_REPROCESSABLE:
        raise ReprocessDocumentBadRequest(
            f"Cannot reprocess from processing_status={status!r}.",
        )
    document.processing_status = "queued"
    document.processing_error = None
    session.flush()


def reprocess_document_for_organization(
    session: Session,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Document | None:
    """Return the org-scoped document after preparing requeue, or ``None`` if missing."""
    doc = get_document_for_organization(
        session, document_id=document_id, organization_id=organization_id
    )
    if doc is None:
        return None
    prepare_document_for_pipeline_reprocess(session, document=doc)
    return doc
