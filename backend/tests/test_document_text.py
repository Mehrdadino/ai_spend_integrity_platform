"""Unit tests for embedded PDF text extraction (pypdf) and scan detection."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.services.document_text import (
    DocumentTextExtractionError,
    _classify_pdf_text,
    extract_text_for_document,
    extract_text_from_pdf_bytes,
    truncate_text_for_llm,
)


class TestClassifyPdfText(unittest.TestCase):
    def test_usable_digital_pdf(self) -> None:
        has_usable, needs_ocr = _classify_pdf_text(
            text="a" * 100,
            page_count=2,
            mime_type="application/pdf",
            min_chars_total=40,
            min_chars_per_page=25,
        )
        self.assertTrue(has_usable)
        self.assertFalse(needs_ocr)

    def test_scan_needs_ocr(self) -> None:
        has_usable, needs_ocr = _classify_pdf_text(
            text="",
            page_count=3,
            mime_type="application/pdf",
            min_chars_total=40,
            min_chars_per_page=25,
        )
        self.assertFalse(has_usable)
        self.assertTrue(needs_ocr)

    def test_image_mime_needs_ocr(self) -> None:
        has_usable, needs_ocr = _classify_pdf_text(
            text="lots of text" * 10,
            page_count=1,
            mime_type="image/png",
            min_chars_total=40,
            min_chars_per_page=25,
        )
        self.assertFalse(has_usable)
        self.assertTrue(needs_ocr)


class TestExtractTextFromPdfBytes(unittest.TestCase):
    def test_empty_body_raises(self) -> None:
        with self.assertRaises(DocumentTextExtractionError):
            extract_text_from_pdf_bytes(b"", min_chars_total=40, min_chars_per_page=25)

    def test_invalid_pdf_raises(self) -> None:
        with self.assertRaises(DocumentTextExtractionError):
            extract_text_from_pdf_bytes(b"not a pdf", min_chars_total=40, min_chars_per_page=25)


class TestExtractTextForDocument(unittest.TestCase):
    def test_skips_non_pdf_mime(self) -> None:
        doc = MagicMock()
        doc.id = "00000000-0000-0000-0000-000000000099"
        doc.mime_type = "text/plain"
        doc.bucket = "b"
        doc.object_key = "k"
        self.assertIsNone(extract_text_for_document(doc))

    def test_image_returns_needs_ocr_without_s3(self) -> None:
        doc = MagicMock()
        doc.mime_type = "image/jpeg"
        result = extract_text_for_document(doc)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.needs_ocr)
        self.assertEqual(result.method, "skipped_image_needs_ocr")


class TestTruncateTextForLlm(unittest.TestCase):
    def test_short_text_unchanged(self) -> None:
        t = "hello"
        self.assertEqual(truncate_text_for_llm(t, max_chars=100), t)

    def test_long_text_truncated(self) -> None:
        t = "x" * 500
        limit = 100
        out = truncate_text_for_llm(t, max_chars=limit)
        self.assertIn("truncated", out)
        self.assertLessEqual(len(out), limit)
