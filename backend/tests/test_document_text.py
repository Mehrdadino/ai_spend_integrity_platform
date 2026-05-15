"""Unit tests for embedded PDF text extraction (pypdf) and scan detection."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.services.document_text import (
    DocumentTextExtractionError,
    DocumentTextResult,
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

    def test_image_ocr_path_calls_ocr_and_returns_text(self) -> None:
        doc = MagicMock()
        doc.mime_type = "image/jpeg"
        doc.bucket = "b"
        doc.object_key = "k"

        with (
            patch(
                "app.services.document_text.get_document_object_bytes",
                return_value=b"fake-img-bytes",
            ),
            patch(
                "app.services.document_text._ocr_tesseract_from_image_bytes",
                return_value=DocumentTextResult(
                    method="tesseract_ocr_image",
                    text="hello",
                    page_count=1,
                    char_count=5,
                    chars_per_page=5.0,
                    has_usable_text=True,
                    needs_ocr=False,
                    mime_type="image/jpeg",
                ),
            ),
        ):
            result = extract_text_for_document(doc)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.needs_ocr)
        self.assertEqual(result.method, "tesseract_ocr_image")

    def test_pdf_ocr_path_when_needs_ocr(self) -> None:
        doc = MagicMock()
        doc.mime_type = "application/pdf"
        doc.bucket = "b"
        doc.object_key = "k"
        doc.id = "00000000-0000-0000-0000-000000000099"

        embedded_result = DocumentTextResult(
            method="pypdf_embedded",
            text="",
            page_count=2,
            char_count=0,
            chars_per_page=0.0,
            has_usable_text=False,
            needs_ocr=True,
            mime_type="application/pdf",
        )

        ocr_result = DocumentTextResult(
            method="tesseract_ocr_pdf",
            text="bill line 1",
            page_count=2,
            char_count=12,
            chars_per_page=6.0,
            has_usable_text=True,
            needs_ocr=False,
            mime_type="application/pdf",
        )

        with (
            patch(
                "app.services.document_text.get_document_object_bytes",
                return_value=b"fake-pdf-bytes",
            ),
            patch(
                "app.services.document_text.extract_text_from_pdf_bytes",
                return_value=embedded_result,
            ),
            patch(
                "app.services.document_text._ocr_tesseract_from_pdf_bytes",
                return_value=ocr_result,
            ),
        ):
            result = extract_text_for_document(doc)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.method, "tesseract_ocr_pdf")
        self.assertFalse(result.needs_ocr)


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
