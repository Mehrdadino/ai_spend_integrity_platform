"""Unit tests for §3b comparison rule pack (no database)."""

from __future__ import annotations

import unittest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from app.constants.normalization import (
    LINE_KIND_CHARGE,
    LINE_KIND_CREDIT,
    LINE_KIND_FEE,
    LINE_KIND_TAX,
    SPEND_DOMAIN_TELECOM,
)
from app.services.normalization.service_keys import SERVICE_UTILITY_ELECTRIC
from app.models.bill import Bill
from app.models.bill_line_item import BillLineItem
from app.services.comparison.rule_pack_v1 import evaluate_rule_pack_v1


def _bill(
    *,
    bill_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
    total: str | None = None,
    spend_domain: str = "utility",
    spend_kind: str | None = "electricity",
    period_end: date | None = date(2026, 3, 31),
    period_start: date | None = None,
    summary: dict | None = None,
    line_items: list[BillLineItem] | None = None,
) -> Bill:
    bid = bill_id or uuid.uuid4()
    b = Bill(
        id=bid,
        organization_id=uuid.uuid4(),
        site_id=site_id or uuid.uuid4(),
        document_id=uuid.uuid4(),
        spend_domain=spend_domain,
        spend_kind=spend_kind,
        currency="USD",
        summary=summary,
        normalization_version="norm-v1",
        period_start=period_start,
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

    def test_no_prior_still_runs_header_mismatch(self) -> None:
        current = _bill(
            total="100.00",
            line_items=[
                _line(kind=LINE_KIND_CHARGE, label="A", amount="40.00"),
                _line(kind=LINE_KIND_CHARGE, label="B", amount="50.00"),
            ],
        )
        findings, compared = evaluate_rule_pack_v1(current=current, priors=[])
        self.assertIsNone(compared)
        rules = {f.rule_id for f in findings}
        self.assertIn("header_total_mismatch", rules)
        self.assertIn("no_prior_bill", rules)

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

    def test_duplicate_line_fingerprint_without_prior(self) -> None:
        dup = _line(kind=LINE_KIND_CHARGE, label="Energy charge", amount="50.00", position=1)
        dup2 = _line(kind=LINE_KIND_CHARGE, label="Energy charge", amount="50.00", position=2)
        current = _bill(total="100.00", line_items=[dup, dup2])
        findings, compared = evaluate_rule_pack_v1(current=current, priors=[])
        self.assertIsNone(compared)
        dup_find = next(f for f in findings if f.rule_id == "duplicate_line_fingerprint")
        self.assertEqual(dup_find.severity, "warning")
        self.assertEqual(dup_find.evidence["duplicate_groups"][0]["count"], 2)

    def test_fees_high_share_without_prior(self) -> None:
        current = _bill(
            total="100.00",
            line_items=[
                _line(kind=LINE_KIND_CHARGE, label="Usage", amount="70.00", position=1),
                _line(kind=LINE_KIND_FEE, label="Rider surcharge", amount="20.00", position=2),
            ],
        )
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[])
        fees = next(f for f in findings if f.rule_id == "fees_high_share_of_total")
        self.assertEqual(fees.severity, "warning")

    def test_penalty_style_fees_without_prior(self) -> None:
        current = _bill(
            total="110.00",
            line_items=[
                _line(kind=LINE_KIND_CHARGE, label="Usage", amount="100.00", position=1),
                _line(kind=LINE_KIND_FEE, label="Late payment fee", amount="10.00", position=2),
            ],
        )
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[])
        penalty = next(f for f in findings if f.rule_id == "penalty_style_fees")
        self.assertEqual(penalty.evidence["count"], 1)

    def test_missing_period_dates_warning(self) -> None:
        current = _bill(period_start=None, period_end=None)
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[])
        missing = next(f for f in findings if f.rule_id == "missing_period_dates")
        self.assertEqual(missing.severity, "warning")

    def test_mom_skipped_when_current_has_no_period(self) -> None:
        current = _bill(total="140.00", period_start=None, period_end=None)
        prior = _bill(total="100.00", period_end=date(2026, 2, 28))
        findings, compared = evaluate_rule_pack_v1(current=current, priors=[prior])
        self.assertIsNone(compared)
        rules = {f.rule_id for f in findings}
        self.assertIn("period_comparison_skipped", rules)
        self.assertIn("missing_period_dates", rules)
        self.assertNotIn("mom_total_change", rules)

    def test_mom_skipped_when_prior_has_no_period(self) -> None:
        current = _bill(total="140.00", period_end=date(2026, 3, 31))
        prior = _bill(total="100.00", period_start=None, period_end=None)
        findings, compared = evaluate_rule_pack_v1(current=current, priors=[prior])
        self.assertIsNone(compared)
        self.assertIn("period_comparison_skipped", {f.rule_id for f in findings})
        self.assertNotIn("mom_total_change", {f.rule_id for f in findings})

    def test_new_fee_skipped_when_period_missing(self) -> None:
        prior = _bill(
            total="100.00",
            period_start=None,
            period_end=None,
            line_items=[_line(kind=LINE_KIND_CHARGE, label="Energy charge", amount="100.00")],
        )
        current = _bill(
            total="110.00",
            period_end=date(2026, 3, 31),
            line_items=[
                _line(kind=LINE_KIND_CHARGE, label="Energy charge", amount="100.00", position=1),
                _line(kind=LINE_KIND_FEE, label="Late payment fee", amount="10.00", position=2),
            ],
        )
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[prior])
        rules = {f.rule_id for f in findings}
        self.assertIn("period_comparison_skipped", rules)
        self.assertNotIn("new_fee_lines", rules)

    def test_tax_high_share(self) -> None:
        current = _bill(
            total="100.00",
            line_items=[
                _line(kind=LINE_KIND_CHARGE, label="Usage", amount="70.00", position=1),
                _line(kind=LINE_KIND_TAX, label="Sales tax", amount="12.00", position=2),
            ],
        )
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[])
        tax = next(f for f in findings if f.rule_id == "tax_high_share_of_total")
        self.assertEqual(tax.severity, "warning")

    def test_extraction_structured_fallback(self) -> None:
        current = _bill(
            summary={"structured_via": "deterministic_fallback", "line_count": 1},
            line_items=[_line(kind=LINE_KIND_CHARGE, label="A", amount="10.00")],
        )
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[])
        self.assertIn("extraction_structured_fallback", {f.rule_id for f in findings})

    def test_utility_electric_demand_without_kwh(self) -> None:
        current = _bill(
            spend_kind="electricity",
            line_items=[
                _line(
                    kind=LINE_KIND_CHARGE,
                    label="Demand charge 45 kW",
                    amount="80.00",
                    position=1,
                ),
            ],
        )
        current.line_items[0].canonical_service_key = SERVICE_UTILITY_ELECTRIC
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[])
        self.assertIn("utility_electric_demand_without_usage", {f.rule_id for f in findings})

    def test_telecom_many_fees(self) -> None:
        current = _bill(
            total="100.00",
            spend_domain=SPEND_DOMAIN_TELECOM,
            spend_kind="broadband",
            line_items=[
                _line(kind=LINE_KIND_CHARGE, label="Internet", amount="55.00", position=1),
                _line(kind=LINE_KIND_FEE, label="Fee A", amount="15.00", position=2),
                _line(kind=LINE_KIND_FEE, label="Fee B", amount="15.00", position=3),
                _line(kind=LINE_KIND_FEE, label="Fee C", amount="10.00", position=4),
            ],
        )
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[])
        self.assertIn("telecom_many_fees", {f.rule_id for f in findings})

    def test_credits_exceed_charges(self) -> None:
        current = _bill(
            total="10.00",
            line_items=[
                _line(kind=LINE_KIND_CHARGE, label="Usage", amount="30.00", position=1),
                _line(kind=LINE_KIND_CREDIT, label="Bill credit", amount="-40.00", position=2),
            ],
        )
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[])
        credit = next(f for f in findings if f.rule_id == "credits_exceed_charges")
        self.assertEqual(credit.severity, "warning")


if __name__ == "__main__":
    unittest.main()
