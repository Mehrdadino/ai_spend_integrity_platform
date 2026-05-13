"""Unit tests for 2c normalization helpers (no DB)."""

from __future__ import annotations

import unittest
from decimal import Decimal
from uuid import UUID

from app.constants.extraction import STUB_EXTRACTION_VERSION
from app.constants.normalization import SPEND_DOMAIN_UNSPECIFIED, UNIT_KWH, UNIT_UNKNOWN
from app.models.document import Document
from app.models.document_raw_extraction import DocumentRawExtraction
from app.schemas.extraction.stub_payload import StubDraftLine, StubRawExtractionPayload
from app.services.extraction_validate import validate_raw_extraction_payload
from app.services.normalization.from_extraction import build_bundle_from_stub, build_normalized_bundle
from app.services.normalization.units import canonicalize_quantity_unit


class TestCanonicalizeQuantityUnit(unittest.TestCase):
    def test_kwh_aliases(self) -> None:
        self.assertEqual(canonicalize_quantity_unit("KWH"), UNIT_KWH)
        self.assertEqual(canonicalize_quantity_unit(" kilowatt-hour "), UNIT_KWH)

    def test_unknown_returns_code(self) -> None:
        self.assertEqual(canonicalize_quantity_unit("widgets"), UNIT_UNKNOWN)


class TestStubDraftLinesValidation(unittest.TestCase):
    def test_draft_lines_round_trip_through_2b(self) -> None:
        did = UUID("00000000-0000-0000-0000-000000000099")
        payload = {
            "stub": True,
            "message": "ok",
            "document_id": str(did),
            "mime_type": "application/pdf",
            "spend_domain": "utility",
            "spend_kind": "electricity",
            "draft_lines": [
                {
                    "raw_label": "Energy",
                    "amount": 10.0,
                    "quantity": 5.0,
                    "quantity_unit": "kwh",
                    "service_hint": "electric",
                }
            ],
        }
        out = validate_raw_extraction_payload(
            payload,
            extraction_version=STUB_EXTRACTION_VERSION,
            expected_document_id=did,
        )
        self.assertEqual(len(out["draft_lines"]), 1)
        self.assertEqual(out["draft_lines"][0]["raw_label"], "Energy")


class TestBuildBundleFromStub(unittest.TestCase):
    def test_builds_line_and_total(self) -> None:
        did = UUID("00000000-0000-0000-0000-000000000099")
        doc = Document(
            id=did,
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            site_id=None,
            bucket="b",
            object_key="k",
            sha256="a" * 64,
            mime_type="application/pdf",
            byte_size=1,
            source="upload",
            processing_status="extracted",
        )
        model = StubRawExtractionPayload(
            stub=True,
            message="m",
            document_id=did,
            mime_type="application/pdf",
            spend_domain="utility",
            spend_kind="electricity",
            draft_lines=[
                StubDraftLine(
                    raw_label="Electric delivery",
                    amount=100.0,
                    quantity=50.0,
                    quantity_unit="kwh",
                    service_hint="electric",
                )
            ],
        )
        bundle = build_bundle_from_stub(doc, model)
        self.assertEqual(bundle.spend_domain, "utility")
        self.assertEqual(bundle.total_amount, Decimal("100.0"))
        self.assertEqual(len(bundle.lines), 1)
        self.assertEqual(bundle.lines[0].quantity_unit, UNIT_KWH)

    def test_unknown_extraction_version_minimal_bundle(self) -> None:
        did = UUID("00000000-0000-0000-0000-000000000099")
        doc = Document(
            id=did,
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            site_id=None,
            bucket="b",
            object_key="k",
            sha256="a" * 64,
            mime_type="application/pdf",
            byte_size=1,
            source="upload",
            processing_status="extracted",
        )
        raw = DocumentRawExtraction(
            id=UUID("00000000-0000-0000-0000-0000000000aa"),
            document_id=did,
            raw_payload={"x": 1},
            model_id="m",
            extraction_version="future-v99",
        )
        bundle = build_normalized_bundle(document=doc, raw_row=raw)
        self.assertEqual(bundle.lines, [])
        self.assertEqual(bundle.spend_domain, SPEND_DOMAIN_UNSPECIFIED)

    def test_build_bundle_from_generic(self) -> None:
        did = UUID("00000000-0000-0000-0000-000000000099")
        doc = Document(
            id=did,
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            site_id=None,
            bucket="b",
            object_key="k",
            sha256="a" * 64,
            mime_type="application/pdf",
            byte_size=1,
            source="upload",
            processing_status="extracted",
        )
        from app.schemas.extraction.generic_bill_payload import GenericBillExtractionPayload, GenericBillLineItem
        from app.services.normalization.from_extraction import build_bundle_from_generic

        model = GenericBillExtractionPayload(
            document_id=did,
            spend_domain="telecom",
            spend_kind="fiber",
            issuer_name="ISP Inc",
            currency="USD",
            lines=[GenericBillLineItem(raw_label="Internet service", amount=79.99, service_hint="internet")],
        )
        bundle = build_bundle_from_generic(doc, model)
        self.assertEqual(bundle.spend_domain, "telecom")
        self.assertEqual(bundle.issuer_name, "ISP Inc")
        self.assertEqual(len(bundle.lines), 1)
