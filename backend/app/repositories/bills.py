"""Bill + line-item reads scoped by ``organization_id`` (tenant safety)."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Date, and_, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.bill import Bill
from app.models.document import Document
from app.services.comparison.limits import DEFAULT_SITE_BILL_SCAN, MAX_SITE_BILL_SCAN
from app.services.comparison.period import effective_period_end


def _bill_period_end_expr():
    """SQL ``coalesce(period_end, period_start, created_at::date)`` for consistent ordering."""
    return func.coalesce(
        Bill.period_end,
        Bill.period_start,
        cast(Bill.created_at, Date()),
    )


def _clamp_site_scan_limit(limit: int) -> int:
    """Keep site history scans within §3e bounds."""
    return max(1, min(limit, MAX_SITE_BILL_SCAN))


def _bill_is_older_than_current_filter(period_end_col, bill: Bill):
    """SQL filter: rows strictly older than ``bill`` in newest-first site ordering."""
    cur_period = effective_period_end(bill)
    return or_(
        period_end_col < cur_period,
        and_(
            period_end_col == cur_period,
            Bill.created_at < bill.created_at,
        ),
        and_(
            period_end_col == cur_period,
            Bill.created_at == bill.created_at,
            Bill.id < bill.id,
        ),
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
    limit: int = DEFAULT_SITE_BILL_SCAN,
    load_line_items: bool = True,
) -> list[Bill]:
    """All bills for a site in this org, newest billing period first (§3a / §3e).

    ``load_line_items=False`` skips the line-item join for backfill ordering (document ids only).
    """
    period_end = _bill_period_end_expr()
    cap = _clamp_site_scan_limit(limit)
    stmt = (
        select(Bill)
        .join(Document, Document.id == Bill.document_id)
        .where(
            Bill.organization_id == organization_id,
            Bill.site_id == site_id,
            Document.deleted_at.is_(None),
        )
        .order_by(period_end.desc(), Bill.created_at.desc(), Bill.id.desc())
        .limit(cap)
    )
    if load_line_items:
        stmt = stmt.options(selectinload(Bill.line_items))
    return list(session.scalars(stmt).all())


def _list_prior_bills_for_bill_sql(
    session: Session,
    *,
    organization_id: uuid.UUID,
    bill: Bill,
    limit: int,
) -> list[Bill]:
    """Indexed SQL path: fetch up to ``limit`` older same-site bills (no full-site scan)."""
    period_end = _bill_period_end_expr()
    stmt = (
        select(Bill)
        .join(Document, Document.id == Bill.document_id)
        .where(
            Bill.organization_id == organization_id,
            Bill.site_id == bill.site_id,
            Document.deleted_at.is_(None),
            Bill.id != bill.id,
            _bill_is_older_than_current_filter(period_end, bill),
        )
        .order_by(period_end.desc(), Bill.created_at.desc(), Bill.id.desc())
        .limit(max(1, limit))
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
    # SQL path matches newest-first site ordering without loading the full site chain.
    return _list_prior_bills_for_bill_sql(
        session,
        organization_id=organization_id,
        bill=bill,
        limit=limit,
    )


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
