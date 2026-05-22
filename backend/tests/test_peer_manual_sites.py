"""§3c manual peer-site selection (user picker overrides auto discovery)."""

from __future__ import annotations

import unittest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from app.constants.normalization import LINE_KIND_FEE, LINE_KIND_USAGE
from app.models.bill import Bill
from app.models.bill_line_item import BillLineItem
from app.services.comparison.peer_pack_v1 import evaluate_peer_pack_v1
from app.services.comparison.peer_sites import normalize_user_peer_site_ids
from app.services.normalization.service_keys import SERVICE_UTILITY_ELECTRIC


def _bill(
    *,
    site_id: uuid.UUID,
    period_end: date = date(2026, 3, 31),
    fee_label: str | None = None,
) -> Bill:
    bid = uuid.uuid4()
    lines: list[BillLineItem] = [
        BillLineItem(
            id=uuid.uuid4(),
            bill_id=bid,
            position=1,
            raw_label="Energy usage",
            canonical_line_kind=LINE_KIND_USAGE,
            canonical_service_key=SERVICE_UTILITY_ELECTRIC,
            quantity=Decimal("820"),
            quantity_unit="kwh",
            amount=Decimal("98.40"),
            currency="USD",
        ),
    ]
    if fee_label:
        lines.append(
            BillLineItem(
                id=uuid.uuid4(),
                bill_id=bid,
                position=2,
                raw_label=fee_label,
                canonical_line_kind=LINE_KIND_FEE,
                amount=Decimal("15"),
                currency="USD",
            )
        )
    b = Bill(
        id=bid,
        organization_id=uuid.uuid4(),
        site_id=site_id,
        document_id=uuid.uuid4(),
        spend_domain="utility",
        spend_kind="electricity",
        currency="USD",
        normalization_version="norm-v1",
        period_end=period_end,
        period_start=date(2026, 3, 1),
        created_at=datetime(2026, 3, 15, tzinfo=timezone.utc),
        total_amount=Decimal("120"),
    )
    b.line_items = lines
    return b


class TestPeerManualSites(unittest.TestCase):
    def test_normalize_drops_anchor_site(self) -> None:
        anchor_site = uuid.uuid4()
        other = uuid.uuid4()
        anchor = _bill(site_id=anchor_site)
        out = normalize_user_peer_site_ids(anchor, [other, anchor_site, other])
        self.assertEqual(out, [other])

    def test_manual_selection_one_peer_can_run(self) -> None:
        anchor_site = uuid.uuid4()
        peer_site = uuid.uuid4()
        anchor = _bill(site_id=anchor_site, fee_label="Grid modernization surcharge")
        peer = _bill(site_id=peer_site)
        findings = evaluate_peer_pack_v1(
            anchor=anchor,
            peer_candidates=[peer],
            user_selected_peer_site_ids=[peer_site],
        )
        rule_ids = {f.rule_id for f in findings}
        self.assertIn("peer_fee_line_rare", rule_ids)

    def test_sql_peer_site_filter_passed_to_repository(self) -> None:
        from app.repositories.bills import list_peer_bill_candidates_for_anchor

        session = MagicMock()
        anchor = _bill(site_id=uuid.uuid4())
        peer_id = uuid.uuid4()
        session.scalars.return_value.all.return_value = []
        list_peer_bill_candidates_for_anchor(
            session,
            organization_id=anchor.organization_id,
            anchor=anchor,
            window_start=date(2026, 3, 1),
            window_end=date(2026, 3, 31),
            peer_site_ids=[peer_id],
        )
        session.scalars.assert_called_once()


if __name__ == "__main__":
    unittest.main()
