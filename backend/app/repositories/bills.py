"""Bill + line-item reads scoped by ``organization_id`` (tenant safety)."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.bill import Bill
from app.models.document import Document
from app.services.comparison.period import select_prior_bills

# Cap rows loaded per site when selecting priors (3a); §3e can add indexed SQL cursors later.
_DEFAULT_SITE_BILL_SCAN = 200


def _bill_period_end_expr():
    """SQL ``coalesce(period_end, period_start, created_at::date)`` for consistent ordering."""
    return func.coalesce(
        Bill.period_end,
        Bill.period_start,
        cast(Bill.created_at, Date()),
    )


def get_bill_for_org_document(
    session: Session,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Optional[Bill]:
    """Return ``Bill`` with ``line_items`` loaded, or ``None`` if missing or wrong org."""
    stmt = (
        select(Bill)
        .join(Document, Document.id == Bill.document_id)
        .where(
            Bill.document_id == document_id,
            Document.organization_id == organization_id,
            Document.deleted_at.is_(None),
        )
        .options(selectinload(Bill.line_items))
    )
    return session.scalar(stmt)


def list_bills_for_site(
    session: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID,
    limit: int = _DEFAULT_SITE_BILL_SCAN,
) -> list[Bill]:
    """All bills for a site in this org, newest billing period first (§3a)."""
    period_end = _bill_period_end_expr()
    stmt = (
        select(Bill)
        .join(Document, Document.id == Bill.document_id)
        .where(
            Bill.organization_id == organization_id,
            Bill.site_id == site_id,
            Document.deleted_at.is_(None),
        )
        .order_by(period_end.desc(), Bill.created_at.desc(), Bill.id.desc())
        .limit(max(1, min(limit, 500)))
        .options(selectinload(Bill.line_items))
    )
    return list(session.scalars(stmt).all())


def get_prior_bills_for_bill(
    session: Session,
    *,
    organization_id: uuid.UUID,
    bill: Bill,
    limit: int = 10,
) -> list[Bill]:
    """Up to ``limit`` older bills for the same ``site_id`` (empty if ``bill.site_id`` is null)."""
    if bill.site_id is None:
        return []
    if bill.organization_id != organization_id:
        return []
    ordered = list_bills_for_site(
        session,
        organization_id=organization_id,
        site_id=bill.site_id,
    )
    return select_prior_bills(ordered, bill.id, limit=limit)


def get_prior_bills_for_org_document(
    session: Session,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    limit: int = 10,
) -> tuple[Optional[Bill], list[Bill]]:
    """Return ``(current_bill, prior_bills)`` for a document, or ``(None, [])`` when no bill row."""
    current = get_bill_for_org_document(
        session,
        organization_id=organization_id,
        document_id=document_id,
    )
    if current is None:
        return None, []
    priors = get_prior_bills_for_bill(
        session,
        organization_id=organization_id,
        bill=current,
        limit=limit,
    )
    return current, priors
