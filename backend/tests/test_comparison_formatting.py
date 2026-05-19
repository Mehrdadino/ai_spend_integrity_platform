"""Display formatting for comparison money and percentages."""

from __future__ import annotations

import unittest
from decimal import Decimal

from app.services.comparison.formatting import format_money, format_percent, format_percent_from_float
from app.services.comparison.rule_pack_v1 import evaluate_rule_pack_v1


class TestComparisonFormatting(unittest.TestCase):
    def test_format_money_two_places(self) -> None:
        self.assertEqual(format_money(Decimal("73.6")), "73.60")
        self.assertEqual(format_money(Decimal("100")), "100.00")

    def test_format_percent_two_places(self) -> None:
        self.assertEqual(
            format_percent(Decimal("51.64912280701754385964912281")),
            "51.65",
        )

    def test_format_percent_from_float(self) -> None:
        self.assertEqual(format_percent_from_float(15.0), "15.00")

    def test_mom_summary_uses_two_decimal_places(self) -> None:
        import uuid
        from datetime import date, datetime, timezone

        from app.models.bill import Bill

        site = uuid.uuid4()
        prior = Bill(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            site_id=site,
            document_id=uuid.uuid4(),
            spend_domain="utility",
            currency="USD",
            normalization_version="norm-v1",
            period_end=date(2026, 2, 28),
            created_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            total_amount=Decimal("142.40"),
        )
        prior.line_items = []
        current = Bill(
            id=uuid.uuid4(),
            organization_id=prior.organization_id,
            site_id=site,
            document_id=uuid.uuid4(),
            spend_domain="utility",
            currency="USD",
            normalization_version="norm-v1",
            period_end=date(2026, 3, 31),
            created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
            total_amount=Decimal("68.80"),
        )
        current.line_items = []
        findings, _ = evaluate_rule_pack_v1(current=current, priors=[prior])
        mom = next(f for f in findings if f.rule_id == "mom_total_change")
        self.assertIn("73.60 USD", mom.summary)
        self.assertIn("(51.69%)", mom.summary)
        self.assertNotIn("73.6000", mom.summary)
        self.assertNotIn("51.649", mom.summary)


if __name__ == "__main__":
    unittest.main()
