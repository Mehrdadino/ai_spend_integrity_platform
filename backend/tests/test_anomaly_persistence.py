"""Unit tests for §3d anomaly flattening (rule pack → ``Anomaly`` rows; no database)."""

from __future__ import annotations

import unittest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from app.constants.normalization import LINE_KIND_CHARGE, LINE_KIND_FEE
from app.models.bill import Bill
from app.models.bill_line_item import BillLineItem
from app.schemas.comparison import ComparisonFindingResponse
from app.services.comparison.persist_anomalies import _flatten_findings_into_rows
from app.services.comparison.rule_pack_v1 import evaluate_rule_pack_v1
from app.services.comparison.rules_config import RULE_PACK_VERSION


def _bill(
    *,
    site_id: uuid.UUID | None = None,
    total: str | None = None,
    period_end: date | None = None,
    line_items: list[BillLineItem] | None = None,
) -> Bill:
    bid = uuid.uuid4()
    org_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    b = Bill(
        id=bid,
        organization_id=org_id,
        site_id=site_id if site_id is not None else uuid.uuid4(),
        document_id=doc_id,
        spend_domain="utility",
        currency="USD",
        normalization_version="norm-v1",
        period_end=period_end,
        created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        total_amount=Decimal(total) if total is not None else None,
    )
    items = line_items or []
    for li in items:
        li.bill_id = bid
    b.line_items = items
    return b


def _line(li_id: uuid.UUID, *, kind: str, label: str, amount: str, position: int = 1) -> BillLineItem:
    return BillLineItem(
        id=li_id,
        bill_id=uuid.uuid4(),
        position=position,
        raw_label=label,
        canonical_line_kind=kind,
        amount=Decimal(amount),
        currency="USD",
    )


class TestAnomalyFlattening(unittest.TestCase):
    def test_new_fee_lines_expand_to_child_rule(self) -> None:
        fid = uuid.uuid4()
        prior = _bill(
            total="100.00",
            line_items=[_line(uuid.uuid4(), kind=LINE_KIND_CHARGE, label="Energy", amount="100.00")],
        )
        current = _bill(
            total="110.00",
            line_items=[
                _line(uuid.uuid4(), kind=LINE_KIND_CHARGE, label="Energy", amount="100.00"),
                _line(fid, kind=LINE_KIND_FEE, label="Late fee", amount="10.00", position=2),
            ],
        )
        findings, comp = evaluate_rule_pack_v1(current=current, priors=[prior])
        self.assertEqual(comp, prior.id)
        rows = _flatten_findings_into_rows(current, findings, comp, RULE_PACK_VERSION)
        child = [r for r in rows if r.rule_id == "new_fee_line"]
        self.assertEqual(len(child), 1)
        self.assertEqual(child[0].bill_line_item_id, fid)
        self.assertEqual(child[0].compared_to_bill_id, prior.id)

    def test_mom_rows_point_at_prior_bill(self) -> None:
        current = _bill(total="115.00")
        prior = _bill(total="100.00")
        findings, comp = evaluate_rule_pack_v1(current=current, priors=[prior])
        rows = _flatten_findings_into_rows(current, findings, comp, RULE_PACK_VERSION)
        mom = next(r for r in rows if r.rule_id == "mom_total_change")
        self.assertEqual(mom.compared_to_bill_id, prior.id)

    def test_header_mismatch_has_no_prior_pointer(self) -> None:
        current = _bill(
            total="100.00",
            line_items=[
                _line(uuid.uuid4(), kind=LINE_KIND_CHARGE, label="A", amount="40.00"),
                _line(uuid.uuid4(), kind=LINE_KIND_CHARGE, label="B", amount="50.00", position=2),
            ],
        )
        prior = _bill(total="90.00")
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[prior])
        rows = _flatten_findings_into_rows(current, findings, prior.id, RULE_PACK_VERSION)
        hdr = next(r for r in rows if r.rule_id == "header_total_mismatch")
        self.assertIsNone(hdr.compared_to_bill_id)

    def test_non_expanded_finding_round_trips_evidence(self) -> None:
        current = _bill()
        finding = ComparisonFindingResponse(
            rule_id="no_prior_bill",
            severity="info",
            title="t",
            summary="s",
            evidence={"k": 1},
        )
        rows = _flatten_findings_into_rows(current, [finding], None, RULE_PACK_VERSION)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].evidence["k"], 1)


if __name__ == "__main__":
    unittest.main()
