"""Org-scoped ``anomalies`` reads (§3d) — hides soft-deleted documents."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.anomaly import Anomaly
from app.models.document import Document
from app.models.site import Site


def list_anomalies_for_organization(
    session: Session,
    *,
    organization_id: uuid.UUID,
    site_id: Optional[uuid.UUID] = None,
    limit: int = 100,
) -> list[Anomaly]:
    """Return persisted comparison signals, newest ``created_at`` first.

    Rows tied to documents with ``deleted_at`` set are excluded so the inbox matches the list UX.
    """
    cap = max(1, min(limit, 500))
    stmt = (
        select(Anomaly)
        .join(Document, Document.id == Anomaly.document_id)
        .where(
            Anomaly.organization_id == organization_id,
            Document.deleted_at.is_(None),
        )
        .options(joinedload(Anomaly.site))
        .order_by(Anomaly.created_at.desc())
        .limit(cap)
    )
    if site_id is not None:
        stmt = stmt.where(Anomaly.site_id == site_id)
    return list(session.scalars(stmt).unique().all())
