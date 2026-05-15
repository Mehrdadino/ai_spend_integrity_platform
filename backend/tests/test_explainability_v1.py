"""Golden tests for §4 template explainability (deterministic; no API/DB)."""

from __future__ import annotations

import unittest

from app.services.explain.anomaly_v1 import build_explainability_v1


class TestExplainabilityV1(unittest.TestCase):
    def test_mom_high_confidence_when_metrics_present(self) -> None:
        ex = build_explainability_v1(
            rule_id="mom_total_change",
            severity="warning",
            evidence={
                "current_total": "115.00",
                "prior_total": "100.00",
                "delta_amount": "15.00",
                "delta_percent": 15.0,
                "currency": "USD",
            },
            summary="Bill total increased…",
        )
        self.assertEqual(ex.confidence, "high")
        self.assertIn("115.00", ex.explanation)
        self.assertIn("100.00", ex.explanation)

    def test_mom_medium_when_field_missing(self) -> None:
        ex = build_explainability_v1(
            rule_id="mom_total_change",
            severity="warning",
            evidence={"current_total": "115.00", "prior_total": "100.00"},
            summary="x",
        )
        self.assertEqual(ex.confidence, "medium")

    def test_header_mismatch(self) -> None:
        ex = build_explainability_v1(
            rule_id="header_total_mismatch",
            severity="warning",
            evidence={
                "header_total": "100.00",
                "lines_sum": "90.00",
                "difference": "10.00",
                "currency": "USD",
            },
            summary="hdr",
        )
        self.assertEqual(ex.confidence, "high")
        self.assertIn("90.00", ex.explanation)

    def test_new_fee_line(self) -> None:
        ex = build_explainability_v1(
            rule_id="new_fee_line",
            severity="warning",
            evidence={
                "line": {"raw_label": "Late fee", "amount": "10.00", "currency": "USD"},
                "prior_bill_id": "abc",
                "prior_period_end": "2026-02-28",
            },
            summary="fee",
        )
        self.assertIn("Late fee", ex.explanation)
        self.assertEqual(ex.confidence, "high")

    def test_no_prior_info(self) -> None:
        ex = build_explainability_v1(
            rule_id="no_prior_bill",
            severity="info",
            evidence={},
            summary="Upload an older bill.",
        )
        self.assertEqual(ex.confidence, "high")
        self.assertIn("no older", ex.explanation.lower())

    def test_unknown_rule_falls_back(self) -> None:
        ex = build_explainability_v1(
            rule_id="future_rule_xyz",
            severity="info",
            evidence={},
            summary="Short note.",
        )
        self.assertEqual(ex.confidence, "medium")
        self.assertIn("future_rule_xyz", ex.explanation)


if __name__ == "__main__":
    unittest.main()
