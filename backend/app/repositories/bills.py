"""Bill + line-item reads scoped by ``organization_id`` (tenant safety)."""

from __future__ import annotations

import uuid
from typing import Iterator, Optional

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


def _bill_is_newer_than_anchor_filter(period_end_col, anchor: Bill):
    """SQL filter: rows strictly newer than ``anchor`` (appear above anchor in newest-first list)."""
    anchor_period = effective_period_end(anchor)
    return or_(
        period_end_col > anchor_period,
        and_(
            period_end_col == anchor_period,
            Bill.created_at > anchor.created_at,
        ),
        and_(
            period_end_col == anchor_period,
            Bill.created_at == anchor.created_at,
            Bill.id > anchor.id,
        ),
    )


def _bill_not_older_than_anchor_filter(period_end_col, anchor: Bill):
    """SQL filter: anchor row and every bill newer than anchor (§3e backfill prefix)."""
    anchor_period = effective_period_end(anchor)
    return or_(
        period_end_col > anchor_period,
        and_(
            period_end_col == anchor_period,
            Bill.created_at > anchor.created_at,
        ),
        and_(
            period_end_col == anchor_period,
            Bill.created_at == anchor.created_at,
            Bill.id >= anchor.id,
        ),
    )


def _site_bills_base_stmt(*, organization_id: uuid.UUID, site_id: uuid.UUID, period_end):
    """Shared org/site/deleted filter for §3e site history queries."""
    return (
        select(Bill.document_id)
        .join(Document, Document.id == Bill.document_id)
        .where(
            Bill.organization_id == organization_id,
            Bill.site_id == site_id,
            Document.deleted_at.is_(None),
        )
        .order_by(period_end.desc(), Bill.created_at.desc(), Bill.id.desc())
    )


def count_bills_newer_than_anchor(
    session: Session,
    *,
    organization_id: uuid.UUID,
    anchor: Bill,
) -> int:
    """How many same-site bills are strictly newer than ``anchor`` (0 ⇒ anchor is newest)."""
    if anchor.site_id is None:
        return 0
    period_end = _bill_period_end_expr()
    stmt = (
        select(func.count())
        .select_from(Bill)
        .join(Document, Document.id == Bill.document_id)
        .where(
            Bill.organization_id == organization_id,
            Bill.site_id == anchor.site_id,
            Document.deleted_at.is_(None),
            Bill.id != anchor.id,
            _bill_is_newer_than_anchor_filter(period_end, anchor),
        )
    )
    return int(session.scalar(stmt) or 0)


def list_document_ids_newest_through_anchor(
    session: Session,
    *,
    organization_id: uuid.UUID,
    anchor: Bill,
) -> list[uuid.UUID]:
    """Document IDs needing §3d refresh after ``anchor`` lands (indexed SQL; no full-site load).

    When ``anchor`` is the newest bill, returns at most two IDs (anchor + former newest).
  Otherwise returns the newest ``count(newer)+1`` bills (prefix through anchor).
    """
    if anchor.site_id is None:
        return [anchor.document_id]

    period_end = _bill_period_end_expr()
    newer_count = count_bills_newer_than_anchor(
        session, organization_id=organization_id, anchor=anchor
    )
    if newer_count == 0:
        stmt = _site_bills_base_stmt(
            organization_id=organization_id,
            site_id=anchor.site_id,
            period_end=period_end,
        ).limit(2)
        rows = list(session.scalars(stmt).all())
        if anchor.document_id in rows:
            return rows
        return [anchor.document_id] + [d for d in rows if d != anchor.document_id][:1]

    limit = newer_count + 1
    stmt = (
        _site_bills_base_stmt(
            organization_id=organization_id,
            site_id=anchor.site_id,
            period_end=period_end,
        )
        .where(_bill_not_older_than_anchor_filter(period_end, anchor))
        .limit(limit)
    )
    doc_ids = list(session.scalars(stmt).all())
    if anchor.document_id not in doc_ids:
        # Anchor missing from prefix (data race) — still evaluate it once.
        return [anchor.document_id]
    return doc_ids


def iter_document_ids_for_site_keyset(
    session: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID,
    page_size: int,
    max_bills: int = 0,
) -> Iterator[uuid.UUID]:
    """Yield every ``document_id`` on a site, newest first, using keyset pages (§3e scale)."""
    period_end = _bill_period_end_expr()
    last_period: Optional[Date] = None
    last_created_at = None
    last_id: Optional[uuid.UUID] = None
    yielded = 0

    while True:
        if max_bills > 0 and yielded >= max_bills:
            return
        stmt = _site_bills_base_stmt(
            organization_id=organization_id,
            site_id=site_id,
            period_end=period_end,
        )
        if last_id is not None and last_period is not None and last_created_at is not None:
            stmt = stmt.where(
                or_(
                    period_end < last_period,
                    and_(period_end == last_period, Bill.created_at < last_created_at),
                    and_(
                        period_end == last_period,
                        Bill.created_at == last_created_at,
                        Bill.id < last_id,
                    ),
                )
            )
        take = page_size
        if max_bills > 0:
            take = min(take, max_bills - yielded)
        stmt = stmt.limit(take)
        page = list(session.scalars(stmt).all())
        if not page:
            return
        for doc_id in page:
            yield doc_id
            yielded += 1
            if max_bills > 0 and yielded >= max_bills:
                return
        if len(page) < take:
            return
        # Advance cursor from the last bill row on this page.
        last_doc_id = page[-1]
        bill_row = get_bill_for_org_document(
            session,
            organization_id=organization_id,
            document_id=last_doc_id,
        )
        if bill_row is None:
            return
        last_period = effective_period_end(bill_row)
        last_created_at = bill_row.created_at
        last_id = bill_row.id


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
