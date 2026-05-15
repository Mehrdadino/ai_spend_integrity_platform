"""Tests for §3e comparison backfill selection (no database)."""

from __future__ import annotations

import unittest
import uuid

from app.services.comparison.backfill import document_ids_newest_through_anchor


class TestComparisonBackfillSelection(unittest.TestCase):
    def test_anchor_in_list_returns_prefix_through_anchor(self) -> None:
        d0 = uuid.uuid4()
        d1 = uuid.uuid4()
        d2 = uuid.uuid4()
        ordered = [d0, d1, d2]  # newest first
        self.assertEqual(document_ids_newest_through_anchor(ordered, d1), [d0, d1])

    def test_anchor_newest_includes_previous_newest_neighbor(self) -> None:
        """Uploading the new top bill shifts the prior for the old newest row."""
        newest = uuid.uuid4()
        previous_newest = uuid.uuid4()
        older = uuid.uuid4()
        ordered = [newest, previous_newest, older]
        self.assertEqual(document_ids_newest_through_anchor(ordered, newest), [newest, previous_newest])

    def test_anchor_newest_single_bill_site(self) -> None:
        only = uuid.uuid4()
        self.assertEqual(document_ids_newest_through_anchor([only], only), [only])

    def test_anchor_missing_returns_only_anchor(self) -> None:
        lone = uuid.uuid4()
        other = uuid.uuid4()
        self.assertEqual(document_ids_newest_through_anchor([other], lone), [lone])


if __name__ == "__main__":
    unittest.main()
