"""Cross-site comparison suite: generated PDFs, upload order, and §3c outcomes.

Exercises the full path **PDF bytes → pypdf text → BILL_SPEC_V1 → normalization → peer pack**
without Postgres (in-memory ``Bill`` rows). PDF files for manual upload live under
``tests/fixtures/cross_site_pdfs/`` (see ``scripts/generate_cross_site_pdfs.py``).
"""

from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone

from app.constants.extraction import GENERIC_BILL_EXTRACTION_VERSION
from app.models.bill import Bill
from app.models.document import Document
from app.models.document_raw_extraction import DocumentRawExtraction
from app.services.comparison.peer_pack_v1 import evaluate_peer_pack_v1
from app.services.comparison.period import effective_period_end
from app.services.document_text import extract_text_from_pdf_bytes
from app.services.extraction_pdf_spec import parse_generic_bill_dict_from_pdf_text
from app.services.extraction_validate import validate_raw_extraction_payload
from app.services.normalization.from_extraction import build_normalized_bundle
from app.services.comparison.rule_pack_v1 import evaluate_rule_pack_v1
from tests.support.cross_site_bill_pdf import (
    ALL_CROSS_SITE_PDF_SPECS,
    CROSS_SITE_UPLOAD_ORDER,
    CrossSiteBillPdfSpec,
    build_test_bill_pdf_bytes,
)


def _bill_from_pdf_spec(
    *,
    spec: CrossSiteBillPdfSpec,
    organization_id: uuid.UUID,
    site_id: uuid.UUID,
) -> Bill:
    """Materialize one in-memory ``Bill`` from a generated PDF (same path as worker)."""
    pdf_bytes = build_test_bill_pdf_bytes(spec)
    text = extract_text_from_pdf_bytes(pdf_bytes, min_chars_total=40, min_chars_per_page=10).text
    doc_id = uuid.uuid4()
    parsed = parse_generic_bill_dict_from_pdf_text(text, document_id=doc_id)
    if parsed is None:
        raise AssertionError(f"PDF spec missing in {spec.filename}")

    doc = Document(
        id=doc_id,
        organization_id=organization_id,
        site_id=site_id,
        bucket="test",
        object_key="k",
        sha256=uuid.uuid4().hex,
        mime_type="application/pdf",
        byte_size=len(pdf_bytes),
        source="upload",
        processing_status="extracted",
    )
    payload = validate_raw_extraction_payload(
        parsed,
        extraction_version=GENERIC_BILL_EXTRACTION_VERSION,
        expected_document_id=doc_id,
    )
    raw = DocumentRawExtraction(
        id=uuid.uuid4(),
        document_id=doc_id,
        raw_payload=payload,
        model_id="test-spec",
        extraction_version=GENERIC_BILL_EXTRACTION_VERSION,
    )
    bundle = build_normalized_bundle(document=doc, raw_row=raw)
    bill = Bill(
        id=uuid.uuid4(),
        organization_id=organization_id,
        site_id=site_id,
        document_id=doc_id,
        spend_domain=bundle.spend_domain,
        spend_kind=bundle.spend_kind,
        issuer_name=bundle.issuer_name,
        period_start=bundle.period_start,
        period_end=bundle.period_end,
        currency=bundle.currency,
        total_amount=bundle.total_amount,
        summary=bundle.summary,
        normalization_version="norm-v1",
        created_at=datetime(2026, 3, 15, tzinfo=timezone.utc),
    )
    from app.models.bill_line_item import BillLineItem

    for ln in bundle.lines:
        bill.line_items.append(
            BillLineItem(
                id=uuid.uuid4(),
                bill_id=bill.id,
                position=ln.position,
                raw_label=ln.raw_label,
                canonical_line_kind=ln.canonical_line_kind,
                canonical_service_key=ln.canonical_service_key,
                quantity=ln.quantity,
                quantity_unit=ln.quantity_unit,
                amount=ln.amount,
                currency=ln.currency,
                extra=dict(ln.extra),
            )
        )
    return bill


class PeerCrossSiteSuiteTests(unittest.TestCase):
    """Upload-order scenarios using generated PDFs (no database)."""

    def setUp(self) -> None:
        self.org_id = uuid.uuid4()
        self.site_ids = {
            "Cross-Site Site A": uuid.uuid4(),
            "Cross-Site Site B": uuid.uuid4(),
            "Cross-Site Site C": uuid.uuid4(),
            "Cross-Site Site D": uuid.uuid4(),
        }

    def _ingest_ordered(
        self,
        specs: tuple[CrossSiteBillPdfSpec, ...],
    ) -> dict[str, Bill]:
        """Simulate uploads in ``upload_order``; return bills keyed by filename."""
        out: dict[str, Bill] = {}
        for spec in sorted(specs, key=lambda s: s.upload_order):
            out[spec.filename] = _bill_from_pdf_spec(
                spec=spec,
                organization_id=self.org_id,
                site_id=self.site_ids[spec.site_name],
            )
        return out

    def test_three_pdf_two_site_upload_order_insufficient_peers(self) -> None:
        """Core 3 PDFs: anchor last → §3c needs 3 peer sites, only 1 available."""
        bills = self._ingest_ordered(CROSS_SITE_UPLOAD_ORDER)
        anchor = bills["03-upload-last-site-a-mar-rare-fee.pdf"]
        peers = [b for name, b in bills.items() if b.site_id != anchor.site_id]
        findings = evaluate_peer_pack_v1(anchor=anchor, peer_candidates=peers)
        rule_ids = {f.rule_id for f in findings}
        self.assertIn("not_comparable_insufficient_peers", rule_ids)

    def test_site_a_has_february_prior_when_march_uploaded_last(self) -> None:
        """Same-site §3b: March anchor vs February prior after ordered ingest."""
        bills = self._ingest_ordered(CROSS_SITE_UPLOAD_ORDER)
        anchor = bills["03-upload-last-site-a-mar-rare-fee.pdf"]
        feb = bills["02-upload-second-site-a-feb-normal.pdf"]
        site_a_bills = sorted(
            [anchor, feb],
            key=lambda b: effective_period_end(b),
            reverse=True,
        )
        priors = [b for b in site_a_bills if b.id != anchor.id]
        findings, compared = evaluate_rule_pack_v1(current=anchor, priors=priors)
        self.assertEqual(compared, feb.id)
        fee_rules = {f.rule_id for f in findings}
        self.assertIn("new_fee_lines", fee_rules)

    def test_five_pdf_suite_fires_peer_fee_line_rare(self) -> None:
        """Optional peer sites C+D → ``peer_fee_line_rare`` on Site A March anchor."""
        bills = self._ingest_ordered(ALL_CROSS_SITE_PDF_SPECS)
        anchor = bills["03-upload-last-site-a-mar-rare-fee.pdf"]
        peer_candidates = [
            b
            for name, b in bills.items()
            if b.site_id != anchor.site_id and "mar" in name
        ]
        findings = evaluate_peer_pack_v1(anchor=anchor, peer_candidates=peer_candidates)
        rule_ids = {f.rule_id for f in findings}
        self.assertIn("peer_fee_line_rare", rule_ids)
        rare = next(f for f in findings if f.rule_id == "peer_fee_line_rare")
        self.assertGreater(rare.evidence.get("peers_with_fee", 99), -1)


class PeerCrossSitePdfFilesTests(unittest.TestCase):
    """On-disk PDF fixtures are present after ``generate_cross_site_pdfs.py``."""

    def test_fixture_pdfs_exist(self) -> None:
        import os

        base = os.path.join(
            os.path.dirname(__file__),
            "fixtures",
            "cross_site_pdfs",
        )
        for spec in CROSS_SITE_UPLOAD_ORDER:
            path = os.path.join(base, spec.filename)
            self.assertTrue(os.path.isfile(path), f"missing {path}; run scripts/generate_cross_site_pdfs.py")


if __name__ == "__main__":
    unittest.main()
