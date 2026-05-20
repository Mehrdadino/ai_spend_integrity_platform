"""Unit tests for utility-bill validity assessment (``unsupported`` vs ``extracted``)."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import MagicMock

from app.constants.document_processing import (
    UNSUPPORTED_INSUFFICIENT_STRUCTURE,
    UNSUPPORTED_LLM_FALLBACK,
    UNSUPPORTED_NO_LINE_ITEMS,
    UNSUPPORTED_STUB_IGNORED_TEXT,
    UNSUPPORTED_UNSUPPORTED_MIME,
)
from app.constants.normalization import SPEND_DOMAIN_UTILITY
from app.services.document_validity import assess_document_validity
from app.services.normalization.from_extraction import NormalizedBillDraft, NormalizedLineDraft


def _bundle(
    *,
    lines: list[NormalizedLineDraft] | None = None,
    spend_domain: str = SPEND_DOMAIN_UTILITY,
) -> NormalizedBillDraft:
    return NormalizedBillDraft(
        spend_domain=spend_domain,
        spend_kind="electricity",
        total_amount=None,
        currency="USD",
        lines=lines or [],
        summary={},
        issuer_name=None,
        period_start=None,
        period_end=None,
    )


class TestDocumentValidity(unittest.TestCase):
    def test_supported_normal_bill(self) -> None:
        lines = [
            NormalizedLineDraft(
                position=0,
                raw_label="Energy",
                canonical_line_kind="charge",
                canonical_service_key="utility_electric",
                quantity=None,
                quantity_unit=None,
                amount=100,
                currency="USD",
            ),
        ]
        result = assess_document_validity(
            document=MagicMock(),
            bundle=_bundle(lines=lines),
            provenance={"structured_via": "llm", "text_has_usable_text": True},
        )
        self.assertTrue(result.is_utility_bill)

    def test_unsupported_stub_with_usable_text(self) -> None:
        lines = [
            NormalizedLineDraft(
                position=0,
                raw_label="Sample",
                canonical_line_kind="charge",
                canonical_service_key=None,
                quantity=None,
                quantity_unit=None,
                amount=50,
                currency="USD",
            ),
        ]
        result = assess_document_validity(
            document=MagicMock(),
            bundle=_bundle(lines=lines),
            provenance={
                "structured_via": "deterministic_stub",
                "text_has_usable_text": True,
            },
        )
        self.assertFalse(result.is_utility_bill)
        self.assertEqual(result.reason_code, UNSUPPORTED_STUB_IGNORED_TEXT)

    def test_unsupported_llm_fallback(self) -> None:
        result = assess_document_validity(
            document=MagicMock(),
            bundle=_bundle(
                lines=[
                    NormalizedLineDraft(
                        position=0,
                        raw_label="Sample",
                        canonical_line_kind="charge",
                        canonical_service_key=None,
                        quantity=None,
                        quantity_unit=None,
                        amount=10,
                        currency="USD",
                    ),
                ],
            ),
            provenance={"structured_via": "deterministic_fallback"},
        )
        self.assertFalse(result.is_utility_bill)
        self.assertEqual(result.reason_code, UNSUPPORTED_LLM_FALLBACK)

    def test_unsupported_no_lines(self) -> None:
        result = assess_document_validity(
            document=MagicMock(),
            bundle=_bundle(lines=[]),
            provenance={"structured_via": "llm", "text_has_usable_text": True},
        )
        self.assertFalse(result.is_utility_bill)
        self.assertEqual(result.reason_code, UNSUPPORTED_NO_LINE_ITEMS)

    def test_unsupported_unsupported_mime(self) -> None:
        result = assess_document_validity(
            document=MagicMock(),
            bundle=_bundle(lines=[]),
            provenance={"text_extraction_method": "skipped_unsupported_mime"},
        )
        self.assertFalse(result.is_utility_bill)
        self.assertEqual(result.reason_code, UNSUPPORTED_UNSUPPORTED_MIME)

    def test_unsupported_insufficient_structure(self) -> None:
        lines = [
            NormalizedLineDraft(
                position=0,
                raw_label="Note",
                canonical_line_kind="other",
                canonical_service_key=None,
                quantity=None,
                quantity_unit=None,
                amount=None,
                currency="USD",
            ),
        ]
        result = assess_document_validity(
            document=MagicMock(),
            bundle=_bundle(lines=lines),
            provenance={"structured_via": "llm"},
        )
        self.assertFalse(result.is_utility_bill)
        self.assertEqual(result.reason_code, UNSUPPORTED_INSUFFICIENT_STRUCTURE)


if __name__ == "__main__":
    unittest.main()
