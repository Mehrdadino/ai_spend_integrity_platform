"""Unit tests for LLM extraction error surfacing (bill summary UI)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.config import Settings
from app.services.extraction_llm import (
    _http_error_detail,
    format_llm_error_for_ui,
    safe_llm_generic_bill_dict,
)


class TestHttpErrorDetail(unittest.TestCase):
    def test_gemini_json_message(self) -> None:
        body = (
            '{"error":{"code":404,"message":"model gemini-2.0-flash not found",'
            '"status":"NOT_FOUND"}}'
        )
        out = _http_error_detail(404, body)
        self.assertIn("gemini-2.0-flash", out)
        self.assertIn("404", out)


class TestFormatLlmErrorForUi(unittest.TestCase):
    def test_prefixes_and_truncates(self) -> None:
        long_msg = "x" * 600
        out = format_llm_error_for_ui(RuntimeError(long_msg), max_len=100)
        self.assertTrue(out.startswith("LLM structuring failed: "))
        self.assertLessEqual(len(out), 100)


class TestSafeLlmGenericBillDict(unittest.TestCase):
    def test_returns_error_message_on_failure(self) -> None:
        doc = MagicMock()
        doc.id = "00000000-0000-4000-8000-000000000001"
        settings = Settings(extraction_llm_api_key="test-key")

        with patch(
            "app.services.extraction_llm.llm_generic_bill_dict",
            side_effect=RuntimeError("LLM HTTP 401"),
        ):
            payload, err = safe_llm_generic_bill_dict(
                document=doc,
                settings=settings,
                document_text="bill text",
            )

        self.assertIsNone(payload)
        self.assertIn("401", err or "")


if __name__ == "__main__":
    unittest.main()
