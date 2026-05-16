"""Unit tests for §5 review rollup helpers (document list column)."""

from __future__ import annotations

import unittest

from app.services.review.summary import aggregate_review_status_for_document


class TestAggregateReviewStatus(unittest.TestCase):
    def test_empty_returns_none(self) -> None:
        self.assertIsNone(aggregate_review_status_for_document([]))

    def test_flagged_wins_over_open(self) -> None:
        self.assertEqual(
            aggregate_review_status_for_document(["approved", "open", "flagged"]),
            "flagged",
        )

    def test_open_wins_over_dismissed_and_approved(self) -> None:
        self.assertEqual(
            aggregate_review_status_for_document(["approved", "dismissed", "open"]),
            "open",
        )

    def test_single_status(self) -> None:
        self.assertEqual(aggregate_review_status_for_document(["dismissed"]), "dismissed")


if __name__ == "__main__":
    unittest.main()
