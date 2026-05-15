"""Unit tests for §3b comparison rule pack (no database)."""

from __future__ import annotations

import unittest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from app.constants.normalization import LINE_KIND_CHARGE, LINE_KIND_FEE
from app.models.bill import Bill
from app.models.bill_line_item import BillLineItem
from app.services.comparison.rule_pack_v1 import evaluate_rule_pack_v1


def _bill(
    *,
    bill_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
    total: str | None = None,
    period_end: date | None = None,
    line_items: list[BillLineItem] | None = None,
) -> Bill:
    bid = bill_id or uuid.uuid4()
    b = Bill(
        id=bid,
        organization_id=uuid.uuid4(),
        site_id=site_id or uuid.uuid4(),
        document_id=uuid.uuid4(),
        spend_domain="utility",
        currency="USD",
        normalization_version="norm-v1",
        period_end=period_end,
        created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        total_amount=Decimal(total) if total is not None else None,
    )
    if line_items is not None:
        for li in line_items:
            li.bill_id = bid
        b.line_items = line_items
    else:
        b.line_items = []
    return b


def _line(
    *,
    kind: str,
    label: str,
    amount: str | None = None,
    position: int = 1,
) -> BillLineItem:
    return BillLineItem(
        id=uuid.uuid4(),
        bill_id=uuid.uuid4(),
        position=position,
        raw_label=label,
        canonical_line_kind=kind,
        amount=Decimal(amount) if amount is not None else None,
        currency="USD",
    )


class TestRulePackV1(unittest.TestCase):
    def test_no_site_returns_info(self) -> None:
        current = _bill(site_id=None)
        current.site_id = None
        findings, compared = evaluate_rule_pack_v1(current=current, priors=[])
        self.assertIsNone(compared)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule_id, "no_site_assigned")

    def test_no_prior_returns_info(self) -> None:
        current = _bill()
        findings, compared = evaluate_rule_pack_v1(current=current, priors=[])
        self.assertIsNone(compared)
        self.assertEqual(findings[0].rule_id, "no_prior_bill")

    def test_mom_warning_on_15_percent_increase(self) -> None:
        current = _bill(total="115.00", period_end=date(2026, 3, 31))
        prior = _bill(total="100.00", period_end=date(2026, 2, 28))
        findings, compared = evaluate_rule_pack_v1(current=current, priors=[prior])
        self.assertEqual(compared, prior.id)
        mom = [f for f in findings if f.rule_id == "mom_total_change"]
        self.assertEqual(len(mom), 1)
        self.assertEqual(mom[0].severity, "warning")

    def test_mom_critical_on_large_increase(self) -> None:
        current = _bill(total="140.00")
        prior = _bill(total="100.00")
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[prior])
        mom = next(f for f in findings if f.rule_id == "mom_total_change")
        self.assertEqual(mom.severity, "critical")

    def test_new_fee_lines_detected(self) -> None:
        prior = _bill(
            total="100.00",
            line_items=[_line(kind=LINE_KIND_CHARGE, label="Energy charge", amount="100.00")],
        )
        current = _bill(
            total="110.00",
            line_items=[
                _line(kind=LINE_KIND_CHARGE, label="Energy charge", amount="100.00", position=1),
                _line(kind=LINE_KIND_FEE, label="Late payment fee", amount="10.00", position=2),
            ],
        )
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[prior])
        fees = next(f for f in findings if f.rule_id == "new_fee_lines")
        self.assertEqual(fees.evidence["count"], 1)
        self.assertEqual(fees.evidence["new_fee_lines"][0]["raw_label"], "Late payment fee")

    def test_header_total_mismatch(self) -> None:
        current = _bill(
            total="100.00",
            line_items=[
                _line(kind=LINE_KIND_CHARGE, label="A", amount="40.00"),
                _line(kind=LINE_KIND_CHARGE, label="B", amount="50.00"),
            ],
        )
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[_bill(total="90.00")])
        mismatch = next(f for f in findings if f.rule_id == "header_total_mismatch")
        self.assertEqual(mismatch.severity, "warning")

    def test_small_mom_change_no_finding(self) -> None:
        current = _bill(total="102.00")
        prior = _bill(total="100.00")
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[prior])
        self.assertEqual([f.rule_id for f in findings], [])


if __name__ == "__main__":
    unittest.main()
