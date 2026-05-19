"""Unit tests for LLM extraction error surfacing (bill summary UI)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.config import Settings
from app.services.extraction_llm import (
    _extract_assistant_text,
    _http_error_detail,
    _normalize_llm_bill_dict,
    format_llm_error_for_ui,
    safe_llm_generic_bill_dict,
)


class TestHttpErrorDetail(unittest.TestCase):
    def test_list_error_body_does_not_crash(self) -> None:
        body = '[{"error":{"message":"rate limited"}}]'
        out = _http_error_detail(429, body)
        self.assertIn("rate limited", out)

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


class TestLlmResponseCoercion(unittest.TestCase):
    def test_gemini_candidates_parts_shape(self) -> None:
        payload = {"document_id": "x", "lines": [{"raw_label": "Energy", "amount": 12.5}]}
        raw_resp = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            [{"text": __import__("json").dumps(payload)}],
                        ],
                    },
                },
            ],
        }
        text = _extract_assistant_text(raw_resp)
        normalized = _normalize_llm_bill_dict(__import__("json").loads(text))
        self.assertEqual(len(normalized["lines"]), 1)

    def test_error_field_as_list_does_not_crash(self) -> None:
        body = '{"error":[{"message":"model overloaded"}]}'
        out = _http_error_detail(503, body)
        self.assertIn("overloaded", out)

    def test_multipart_content_with_nested_list(self) -> None:
        payload = {"document_id": "x", "lines": []}
        raw_resp = {
            "choices": [
                {
                    "message": {
                        "content": [
                            [{"text": __import__("json").dumps(payload)}],
                        ],
                    },
                },
            ],
        }
        text = _extract_assistant_text(raw_resp)
        normalized = _normalize_llm_bill_dict(__import__("json").loads(text))
        self.assertEqual(normalized["lines"], [])

    def test_lines_dict_with_items_key(self) -> None:
        out = _normalize_llm_bill_dict(
            {
                "document_id": "00000000-0000-4000-8000-000000000001",
                "lines": {"items": [{"raw_label": "Energy", "amount": 10.0}]},
            },
        )
        self.assertEqual(len(out["lines"]), 1)
        self.assertEqual(out["lines"][0]["raw_label"], "Energy")


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
