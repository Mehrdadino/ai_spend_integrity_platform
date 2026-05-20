"""Regression harness: labeled bills must fire (or silence) expected §3b rule_ids."""

from __future__ import annotations

import unittest

from tests.comparison_labeled_cases import build_labeled_cases, run_labeled_accuracy


class TestComparisonLabeledAccuracy(unittest.TestCase):
    """Pilot golden set — extend ``comparison_labeled_cases`` as PDFs are labeled."""

    # Minimum recall on must_include rules across the curated set.
    MIN_RECALL = 1.0

    def test_labeled_cases_recall_and_exclusions(self) -> None:
        report = run_labeled_accuracy(build_labeled_cases())
        self.assertGreaterEqual(report.case_count, 12)
        self.assertGreaterEqual(report.recall, self.MIN_RECALL)
        self.assertEqual(report.exclude_violations, 0, msg=f"unexpected rules: {report.failed_cases}")
        self.assertTrue(report.passed, msg=f"failed cases: {report.failed_cases}")


if __name__ == "__main__":
    unittest.main()
