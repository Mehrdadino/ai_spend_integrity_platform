"""Org-scoped ``anomalies`` reads (§3d) and §5 review event listing — hides soft-deleted documents."""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from typing import Literal, Optional

from sqlalchemy import asc, case, desc, select
from sqlalchemy.orm import Session, joinedload

from app.models.anomaly import Anomaly
from app.models.anomaly_review_event import AnomalyReviewEvent
from app.models.document import Document
from app.services.review.summary import aggregate_review_status_for_document

SortKey = Literal["created_at", "updated_at", "severity"]
SortOrder = Literal["asc", "desc"]


def _base_list_stmt(organization_id: uuid.UUID):
    """Shared join filter: tenant + non-deleted documents (list and single fetch)."""
    return (
        select(Anomaly)
        .join(Document, Document.id == Anomaly.document_id)
        .where(
            Anomaly.organization_id == organization_id,
            Document.deleted_at.is_(None),
        )
    )


def _severity_order_expr():
    """Order: critical > warning > info (for §5c sort=inbox)."""
    return case(
        (Anomaly.severity == "critical", 3),
        (Anomaly.severity == "warning", 2),
        (Anomaly.severity == "info", 1),
        else_=0,
    )


def list_anomalies_for_organization(
    session: Session,
    *,
    organization_id: uuid.UUID,
    site_id: Optional[uuid.UUID] = None,
    review_status: Optional[str] = None,
    sort: SortKey = "created_at",
    order: SortOrder = "desc",
    limit: int = 100,
) -> list[Anomaly]:
    """Return persisted comparison signals (§5c: optional status filter + sort).

    Default ordering: ``created_at`` descending (newest first).
    """
    cap = max(1, min(limit, 500))
    stmt = _base_list_stmt(organization_id).options(joinedload(Anomaly.site))
    if site_id is not None:
        stmt = stmt.where(Anomaly.site_id == site_id)
    if review_status is not None:
        stmt = stmt.where(Anomaly.review_status == review_status.strip().lower())

    sort_col: object
    if sort == "severity":
        sort_col = _severity_order_expr()
    elif sort == "updated_at":
        sort_col = Anomaly.updated_at
    else:
        sort_col = Anomaly.created_at

    if order == "asc":
        stmt = stmt.order_by(asc(sort_col), asc(Anomaly.id))
    else:
        stmt = stmt.order_by(desc(sort_col), desc(Anomaly.id))

    stmt = stmt.limit(cap)
    return list(session.scalars(stmt).unique().all())


def get_anomaly_for_organization(
    session: Session,
    *,
    organization_id: uuid.UUID,
    anomaly_id: uuid.UUID,
) -> Anomaly | None:
    """Fetch one anomaly if it belongs to the org and its document is not soft-deleted."""
    stmt = (
        _base_list_stmt(organization_id)
        .where(Anomaly.id == anomaly_id)
        .options(joinedload(Anomaly.site))
        .limit(1)
    )
    return session.scalar(stmt)


def latest_review_notes_for_anomaly_ids(
    session: Session,
    *,
    organization_id: uuid.UUID,
    anomaly_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, str]:
    """Most recent non-empty §5e note per anomaly (newest ``anomaly_review_events`` row)."""
    if not anomaly_ids:
        return {}
    stmt = (
        select(AnomalyReviewEvent)
        .where(
            AnomalyReviewEvent.organization_id == organization_id,
            AnomalyReviewEvent.anomaly_id.in_(tuple(anomaly_ids)),
            AnomalyReviewEvent.note.is_not(None),
        )
        .order_by(AnomalyReviewEvent.anomaly_id, desc(AnomalyReviewEvent.created_at))
    )
    out: dict[uuid.UUID, str] = {}
    for event in session.scalars(stmt):
        if event.anomaly_id in out:
            continue
        text = (event.note or "").strip()
        if text:
            out[event.anomaly_id] = text
    return out


def review_status_by_document_ids(
    session: Session,
    *,
    organization_id: uuid.UUID,
    document_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, str]:
    """Aggregate ``anomalies.review_status`` per document (attention-first; §5 inbox rollup)."""
    if not document_ids:
        return {}
    stmt = (
        select(Anomaly.document_id, Anomaly.review_status)
        .join(Document, Document.id == Anomaly.document_id)
        .where(
            Anomaly.organization_id == organization_id,
            Anomaly.document_id.in_(tuple(document_ids)),
            Document.deleted_at.is_(None),
        )
    )
    by_document: dict[uuid.UUID, list[str]] = defaultdict(list)
    for doc_id, status in session.execute(stmt):
        by_document[doc_id].append(status)
    return {
        doc_id: agg
        for doc_id, statuses in by_document.items()
        if (agg := aggregate_review_status_for_document(statuses)) is not None
    }


def list_review_events_for_anomaly(
    session: Session,
    *,
    organization_id: uuid.UUID,
    anomaly_id: uuid.UUID,
) -> list[AnomalyReviewEvent]:
    """Append-only review history for one anomaly (tenant-safe via join)."""
    stmt = (
        select(AnomalyReviewEvent)
        .join(Anomaly, Anomaly.id == AnomalyReviewEvent.anomaly_id)
        .where(
            AnomalyReviewEvent.anomaly_id == anomaly_id,
            Anomaly.organization_id == organization_id,
        )
        .order_by(AnomalyReviewEvent.created_at.asc())
    )
    return list(session.scalars(stmt).all())
