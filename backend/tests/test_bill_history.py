"""Unit tests for §3a bill period ordering and prior-bill selection (no DB)."""

from __future__ import annotations

import unittest
import uuid
from datetime import date, datetime, timezone
from app.models.bill import Bill
from app.services.comparison.period import (
    bill_period_sort_key,
    effective_period_end,
    is_bill_older_than,
    select_prior_bills,
)


def _bill(
    *,
    bill_id: uuid.UUID | None = None,
    period_end: date | None = None,
    period_start: date | None = None,
    created_at: datetime | None = None,
) -> Bill:
    """Minimal ``Bill`` ORM instance for ordering tests (not persisted)."""
    return Bill(
        id=bill_id or uuid.uuid4(),
        organization_id=uuid.uuid4(),
        site_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        spend_domain="utility",
        currency="USD",
        normalization_version="norm-v1",
        period_start=period_start,
        period_end=period_end,
        created_at=created_at or datetime(2026, 1, 15, tzinfo=timezone.utc),
    )


class TestEffectivePeriodEnd(unittest.TestCase):
    def test_prefers_period_end(self) -> None:
        b = _bill(period_end=date(2026, 3, 1), period_start=date(2026, 2, 1))
        self.assertEqual(effective_period_end(b), date(2026, 3, 1))

    def test_falls_back_to_period_start(self) -> None:
        b = _bill(period_start=date(2026, 2, 1))
        self.assertEqual(effective_period_end(b), date(2026, 2, 1))

    def test_falls_back_to_created_at_date(self) -> None:
        b = _bill(created_at=datetime(2026, 5, 10, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(effective_period_end(b), date(2026, 5, 10))


class TestIsBillOlderThan(unittest.TestCase):
    def test_older_by_period_end(self) -> None:
        current = _bill(period_end=date(2026, 3, 1))
        older = _bill(period_end=date(2026, 2, 1))
        self.assertTrue(is_bill_older_than(current, older))
        self.assertFalse(is_bill_older_than(older, current))

    def test_tie_breaks_on_created_at_then_id(self) -> None:
        shared = date(2026, 3, 1)
        earlier = _bill(
            bill_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
            period_end=shared,
            created_at=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
        )
        later = _bill(
            bill_id=uuid.UUID("00000000-0000-4000-8000-000000000002"),
            period_end=shared,
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(is_bill_older_than(later, earlier))
        self.assertFalse(is_bill_older_than(earlier, later))


class TestSelectPriorBills(unittest.TestCase):
    def test_returns_older_bills_after_current_in_newest_first_list(self) -> None:
        b_new = _bill(period_end=date(2026, 3, 1))
        b_mid = _bill(period_end=date(2026, 2, 1))
        b_old = _bill(period_end=date(2026, 1, 1))
        ordered = sorted([b_new, b_mid, b_old], key=bill_period_sort_key, reverse=True)
        priors = select_prior_bills(ordered, b_new.id, limit=10)
        self.assertEqual([p.id for p in priors], [b_mid.id, b_old.id])

    def test_respects_limit(self) -> None:
        bills = [_bill(period_end=date(2026, m, 1)) for m in (3, 2, 1)]
        ordered = sorted(bills, key=bill_period_sort_key, reverse=True)
        priors = select_prior_bills(ordered, bills[0].id, limit=1)
        self.assertEqual(len(priors), 1)
        self.assertEqual(priors[0].id, bills[1].id)

    def test_empty_when_current_not_in_list(self) -> None:
        b = _bill()
        priors = select_prior_bills([_bill()], b.id, limit=5)
        self.assertEqual(priors, [])


if __name__ == "__main__":
    unittest.main()
