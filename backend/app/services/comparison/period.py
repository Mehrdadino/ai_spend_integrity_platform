"""Bill period ordering for §3a prior-bill queries.

**Period key (newest first):** ``coalesce(period_end, period_start, created_at.date())``,
then ``created_at`` timestamp, then ``bill.id`` for stable ties.

Bills with no ``site_id`` are not comparable across history until a site is assigned.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Sequence
from uuid import UUID

from app.models.bill import Bill

# Shown on API responses so clients know how "prior" was defined.
BILL_ORDERING_NOTE = (
    "Prior bills: same organization and site_id, newest-first by "
    "coalesce(period_end, period_start, created_at date), then created_at, then id."
)


def effective_period_end(bill: Bill) -> date:
    """Single date used to sort bills into billing periods when headers are sparse."""
    if bill.period_end is not None:
        return bill.period_end
    if bill.period_start is not None:
        return bill.period_start
    return bill.created_at.date()


def bill_period_sort_key(bill: Bill) -> tuple[date, datetime, UUID]:
    """Descending-sort key: larger tuple = more recent bill."""
    return (effective_period_end(bill), bill.created_at, bill.id)


def is_bill_older_than(current: Bill, candidate: Bill) -> bool:
    """True when ``candidate`` is strictly older than ``current`` (newest-first site order)."""
    return bill_period_sort_key(candidate) < bill_period_sort_key(current)


def select_prior_bills(
    ordered_newest_first: Sequence[Bill],
    current_bill_id: UUID,
    *,
    limit: int,
) -> list[Bill]:
    """Return up to ``limit`` bills strictly *older* than ``current_bill_id`` in ``ordered_newest_first``."""
    if limit <= 0:
        return []
    prior: list[Bill] = []
    seen_current = False
    for bill in ordered_newest_first:
        if bill.id == current_bill_id:
            seen_current = True
            continue
        if seen_current:
            prior.append(bill)
            if len(prior) >= limit:
                break
    return prior
