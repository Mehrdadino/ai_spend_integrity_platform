"""Document queries with mandatory organization scope (defense in depth)."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document


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
