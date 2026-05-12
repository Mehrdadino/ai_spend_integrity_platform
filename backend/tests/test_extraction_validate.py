"""Unit tests for extraction payload validation (2b; no DB)."""

from __future__ import annotations

import unittest
from uuid import UUID

from app.services.extraction_validate import (
    ExtractionPayloadValidationError,
    validate_raw_extraction_payload,
)
from app.constants.extraction import STUB_EXTRACTION_VERSION


class TestValidateStubPayload(unittest.TestCase):
    """Strict stub schema: ``extra`` forbidden, ``document_id`` must match."""

    def test_valid_returns_json_safe_dict(self) -> None:
        did = UUID("00000000-0000-0000-0000-000000000099")
        payload = {
            "stub": True,
            "message": "ok",
            "document_id": str(did),
            "mime_type": "application/pdf",
        }
        out = validate_raw_extraction_payload(
            payload,
            extraction_version=STUB_EXTRACTION_VERSION,
            expected_document_id=did,
        )
        self.assertTrue(out["stub"])
        self.assertEqual(out["mime_type"], "application/pdf")
        self.assertEqual(out["document_id"], str(did))

    def test_extra_key_rejected(self) -> None:
        did = UUID("00000000-0000-0000-0000-000000000099")
        payload = {
            "stub": True,
            "message": "ok",
            "document_id": str(did),
            "mime_type": "application/pdf",
            "surprise": 1,
        }
        with self.assertRaises(ExtractionPayloadValidationError):
            validate_raw_extraction_payload(
                payload,
                extraction_version=STUB_EXTRACTION_VERSION,
                expected_document_id=did,
            )

    def test_document_id_mismatch_rejected(self) -> None:
        did = UUID("00000000-0000-0000-0000-000000000099")
        other = UUID("00000000-0000-0000-0000-000000000088")
        payload = {
            "stub": True,
            "message": "ok",
            "document_id": str(other),
            "mime_type": "application/pdf",
        }
        with self.assertRaises(ExtractionPayloadValidationError):
            validate_raw_extraction_payload(
                payload,
                extraction_version=STUB_EXTRACTION_VERSION,
                expected_document_id=did,
            )


if __name__ == "__main__":
    unittest.main()
