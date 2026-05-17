"""Soft-delete documents (tenant-scoped); object bytes remain in storage for now.

The HTTP delete route also queues §3e site comparison refresh when ``site_id`` is set so
remaining bills at that site get updated priors (see ``comparison_queue``).
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.document import Document
from app.repositories.documents import soft_delete_document_for_organization


def soft_delete_document(
    session: Session,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Document | None:
    """Mark document deleted; return ``None`` when not found or already deleted."""
    return soft_delete_document_for_organization(
        session,
        document_id=document_id,
        organization_id=organization_id,
    )
