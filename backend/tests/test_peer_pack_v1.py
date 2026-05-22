"""Unit tests for §3c cross-site peer rule pack (no database)."""

from __future__ import annotations

import unittest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from app.constants.normalization import LINE_KIND_FEE, LINE_KIND_USAGE
from app.models.bill import Bill
from app.models.bill_line_item import BillLineItem
from app.services.comparison.line_match import line_fingerprint
from app.services.comparison.peer_pack_v1 import evaluate_peer_pack_v1, resolve_peer_set
from app.services.normalization.service_keys import SERVICE_UNKNOWN, SERVICE_UTILITY_ELECTRIC


def _bill(
    *,
    site_id: uuid.UUID | None = None,
    total: str = "100.00",
    spend_kind: str = "electricity",
    period_end: date = date(2026, 3, 31),
    line_items: list[BillLineItem] | None = None,
) -> Bill:
    bid = uuid.uuid4()
    b = Bill(
        id=bid,
        organization_id=uuid.uuid4(),
        site_id=site_id or uuid.uuid4(),
        document_id=uuid.uuid4(),
        spend_domain="utility",
        spend_kind=spend_kind,
        currency="USD",
        normalization_version="norm-v1",
        period_end=period_end,
        created_at=datetime(2026, 3, 15, tzinfo=timezone.utc),
        total_amount=Decimal(total),
    )
    b.line_items = line_items or []
    for li in b.line_items:
        li.bill_id = bid
    return b


def _fee_line(label: str, amount: str = "5.00") -> BillLineItem:
    li = BillLineItem(
        id=uuid.uuid4(),
        bill_id=uuid.uuid4(),
        position=1,
        raw_label=label,
        canonical_line_kind=LINE_KIND_FEE,
        canonical_service_key=SERVICE_UTILITY_ELECTRIC,
        amount=Decimal(amount),
        currency="USD",
    )
    return li


def _usage_kwh(qty: str, amount: str = "50.00") -> BillLineItem:
    return BillLineItem(
        id=uuid.uuid4(),
        bill_id=uuid.uuid4(),
        position=2,
        raw_label="Energy charge",
        canonical_line_kind=LINE_KIND_USAGE,
        canonical_service_key=SERVICE_UTILITY_ELECTRIC,
        quantity=Decimal(qty),
        quantity_unit="kwh",
        amount=Decimal(amount),
        currency="USD",
    )


class TestPeerPackV1(unittest.TestCase):
    def test_insufficient_peers_info(self) -> None:
        anchor = _bill()
        peers = [_bill(), _bill()]  # only 2 other sites
        findings = evaluate_peer_pack_v1(anchor=anchor, peer_candidates=peers)
        rule_ids = [f.rule_id for f in findings]
        self.assertIn("not_comparable_insufficient_peers", rule_ids)

    def test_line_fingerprint_uses_label_when_service_unknown(self) -> None:
        li = _fee_line("Grid modernization surcharge", "15.00")
        li.canonical_service_key = SERVICE_UNKNOWN
        self.assertEqual(line_fingerprint(li), "fee|grid modernization surcharge")

    def test_peer_fee_line_rare(self) -> None:
        anchor = _bill(line_items=[_fee_line("Late payment rider", "12.00"), _usage_kwh("100")])
        fp = line_fingerprint(anchor.line_items[0])

        peer_bills = []
        for i in range(3):
            lines = [_usage_kwh("100")]
            if i == 0:
                lines.append(_fee_line("Late payment rider", "12.00"))
            peer_bills.append(_bill(line_items=lines))

        findings = evaluate_peer_pack_v1(anchor=anchor, peer_candidates=peer_bills)
        rare = [f for f in findings if f.rule_id == "peer_fee_line_rare"]
        self.assertTrue(any(f.evidence.get("fingerprint") == fp for f in rare))

    def test_peer_fee_line_widespread(self) -> None:
        anchor = _bill(line_items=[_fee_line("Grid modernization surcharge", "3.00"), _usage_kwh("80")])
        peer_bills = [
            _bill(line_items=[_fee_line("Grid modernization surcharge", "3.00"), _usage_kwh("90")])
            for _ in range(4)
        ]
        findings = evaluate_peer_pack_v1(anchor=anchor, peer_candidates=peer_bills)
        wide = [f for f in findings if f.rule_id == "peer_fee_line_widespread"]
        self.assertEqual(len(wide), 1)
        self.assertGreaterEqual(float(wide[0].evidence.get("prevalence_pct", 0)), 80.0)

    def test_usage_outlier_high_kwh(self) -> None:
        anchor = _bill(total="500.00", line_items=[_usage_kwh("500")])
        peer_bills = [_bill(total="120.00", line_items=[_usage_kwh("100")]) for _ in range(4)]
        findings = evaluate_peer_pack_v1(anchor=anchor, peer_candidates=peer_bills)
        outliers = [f for f in findings if f.rule_id == "peer_usage_or_total_outlier"]
        metrics = {f.evidence.get("metric") for f in outliers}
        self.assertIn("total_kwh", metrics)

    def test_resolve_peer_set_one_per_site(self) -> None:
        site_a = uuid.uuid4()
        older = _bill(site_id=site_a, period_end=date(2026, 3, 1), total="10")
        newer = _bill(site_id=site_a, period_end=date(2026, 3, 28), total="20")
        anchor = _bill()
        resolved = resolve_peer_set(anchor, [older, newer])
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].total_amount, Decimal("20"))


if __name__ == "__main__":
    unittest.main()
