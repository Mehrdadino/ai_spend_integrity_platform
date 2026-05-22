"""Extract comparable numeric metrics from normalized bills for §3c outlier rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from app.constants.normalization import LINE_KIND_USAGE, UNIT_KWH
from app.models.bill import Bill
from app.models.bill_line_item import BillLineItem


@dataclass(frozen=True)
class PeerBillMetrics:
    """Scalar values used by ``peer_usage_or_total_outlier``."""

    bill_total: Decimal | None
    total_kwh: Decimal | None
    cost_per_kwh: Decimal | None
    has_kwh_usage: bool


def extract_peer_metrics(bill: Bill) -> PeerBillMetrics:
    """Summarize bill total and kWh-style usage for peer percentile math."""
    lines = bill.line_items
    total = bill.total_amount
    kwh = _sum_kwh_quantity(lines)
    cost_per: Decimal | None = None
    if total is not None and kwh is not None and kwh > 0:
        cost_per = total / kwh
    return PeerBillMetrics(
        bill_total=total,
        total_kwh=kwh,
        cost_per_kwh=cost_per,
        has_kwh_usage=_bill_has_kwh_usage(lines),
    )


def _bill_has_kwh_usage(lines: Sequence[BillLineItem]) -> bool:
    for li in lines:
        if (li.quantity_unit or "").strip().lower() == UNIT_KWH and li.quantity is not None:
            return True
    return False


def _sum_kwh_quantity(lines: Sequence[BillLineItem]) -> Decimal | None:
    total = Decimal("0")
    found = False
    for li in lines:
        unit = (li.quantity_unit or "").strip().lower()
        if unit != UNIT_KWH and li.canonical_line_kind != LINE_KIND_USAGE:
            continue
        if unit == UNIT_KWH and li.quantity is not None:
            total += li.quantity
            found = True
    return total if found else None
