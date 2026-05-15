"""Document queries with mandatory organization scope (defense in depth).

Active documents have ``deleted_at IS NULL`` (soft delete). List and fetch-by-id
exclude deleted rows so the UI behaves as if the document were removed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document


def _active_document_filters(organization_id: uuid.UUID):
    """Shared tenancy + not-soft-deleted predicate for document reads."""
    return (
        Document.organization_id == organization_id,
        Document.deleted_at.is_(None),
    )


def list_documents_for_organization(
    session: Session,
    *,
    organization_id: uuid.UUID,
    limit: int = 100,
) -> list[Document]:
    """Newest-first ingestion list for step 1h (UI + API); ``limit`` capped by caller."""
    stmt = (
        select(Document)
        .where(*_active_document_filters(organization_id))
        .order_by(Document.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt).all())


def get_document_for_organization(
    session: Session,
    *,
    document_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> Optional[Document]:
    """Fetch one active document only if its ``organization_id`` matches (API safety)."""
    return session.scalar(
        select(Document).where(
            Document.id == document_id,
            *_active_document_filters(organization_id),
        )
    )


def get_document_by_organization_and_sha256(
    session: Session,
    *,
    organization_id: uuid.UUID,
    sha256: str,
) -> Optional[Document]:
    """Active row lookup for upload dedupe (deleted rows do not block re-upload)."""
    return session.scalar(
        select(Document).where(
            Document.organization_id == organization_id,
            Document.sha256 == sha256,
            Document.deleted_at.is_(None),
        )
    )


def soft_delete_document_for_organization(
    session: Session,
    *,
    document_id: uuid.UUID,
    organization_id: uuid.UUID,
    deleted_at: datetime | None = None,
) -> Optional[Document]:
    """Set ``deleted_at`` on the row; return ``None`` if missing or already deleted."""
    doc = session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == organization_id,
            Document.deleted_at.is_(None),
        )
    )
    if doc is None:
        return None
    doc.deleted_at = deleted_at or datetime.now(timezone.utc)
    session.flush()
    return doc
