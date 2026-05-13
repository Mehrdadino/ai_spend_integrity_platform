"""Document queries with mandatory organization scope (defense in depth).

Includes org-scoped list for the ingestion status API (step 1h).
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document


def list_documents_for_organization(
    session: Session,
    *,
    organization_id: uuid.UUID,
    limit: int = 100,
) -> list[Document]:
    """Newest-first ingestion list for step 1h (UI + API); ``limit`` capped by caller."""
    stmt = (
        select(Document)
        .where(Document.organization_id == organization_id)
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
    """Fetch one document only if its ``organization_id`` matches (API safety)."""
    return session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == organization_id,
        )
    )


def get_document_by_organization_and_sha256(
    session: Session,
    *,
    organization_id: uuid.UUID,
    sha256: str,
) -> Optional[Document]:
    """Used after ``DuplicateDocumentError`` to return the existing row id (idempotency)."""
    return session.scalar(
        select(Document).where(
            Document.organization_id == organization_id,
            Document.sha256 == sha256,
        )
    )
