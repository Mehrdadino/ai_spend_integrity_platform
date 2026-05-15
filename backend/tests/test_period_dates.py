"""Tests for billing period date parsing (generic-bill-v1)."""

from __future__ import annotations

import unittest
from datetime import date
from uuid import UUID

from app.constants.extraction import GENERIC_BILL_EXTRACTION_VERSION
from app.schemas.extraction.generic_bill_payload import GenericBillExtractionPayload
from app.services.extraction_validate import validate_raw_extraction_payload
from app.schemas.extraction.period_dates import parse_bill_period_date


class TestParseBillPeriodDate(unittest.TestCase):
    def test_iso_date(self) -> None:
        self.assertEqual(parse_bill_period_date("2025-03-01"), date(2025, 3, 1))

    def test_us_slash_date(self) -> None:
        self.assertEqual(parse_bill_period_date("03/15/2025"), date(2025, 3, 15))


class TestGenericBillPeriodFields(unittest.TestCase):
    def test_period_fields_round_trip(self) -> None:
        did = UUID("00000000-0000-0000-0000-000000000099")
        payload = {
            "document_id": str(did),
            "currency": "USD",
            "period_start": "2025-02-01",
            "period_end": "2025-02-28",
            "lines": [{"raw_label": "Energy", "amount": 10.0}],
        }
        out = validate_raw_extraction_payload(
            payload,
            extraction_version=GENERIC_BILL_EXTRACTION_VERSION,
            expected_document_id=did,
        )
        self.assertEqual(out["period_start"], "2025-02-01")
        self.assertEqual(out["period_end"], "2025-02-28")

    def test_period_end_before_start_rejected(self) -> None:
        did = UUID("00000000-0000-0000-0000-000000000099")
        with self.assertRaises(Exception):
            GenericBillExtractionPayload(
                document_id=did,
                currency="USD",
                period_start="2025-03-01",
                period_end="2025-02-01",
                lines=[],
            )


if __name__ == "__main__":
    unittest.main()
