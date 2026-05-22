"""Tests for ``BILL_SPEC_V1`` parsing from embedded PDF text."""

from __future__ import annotations

import unittest
import uuid

from app.services.extraction_pdf_spec import (
    parse_generic_bill_dict_from_pdf_text,
    pdf_text_contains_bill_spec,
)
from tests.support.cross_site_bill_pdf import CROSS_SITE_UPLOAD_ORDER, build_test_bill_pdf_bytes
from app.services.document_text import extract_text_from_pdf_bytes


class TestExtractionPdfSpec(unittest.TestCase):
    def test_generated_pdf_contains_spec_and_parses(self) -> None:
        spec = CROSS_SITE_UPLOAD_ORDER[2]
        pdf_bytes = build_test_bill_pdf_bytes(spec)
        text = extract_text_from_pdf_bytes(pdf_bytes, min_chars_total=40, min_chars_per_page=10).text
        self.assertTrue(pdf_text_contains_bill_spec(text))
        did = uuid.uuid4()
        parsed = parse_generic_bill_dict_from_pdf_text(text, document_id=did)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["document_id"], str(did))
        self.assertEqual(parsed["spend_kind"], "electricity")
        labels = [ln["raw_label"] for ln in parsed["lines"]]
        self.assertIn("Grid modernization surcharge", labels)


if __name__ == "__main__":
    unittest.main()
