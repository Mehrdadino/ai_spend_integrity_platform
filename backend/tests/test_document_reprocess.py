"""Unit tests for ``document_reprocess`` (requeue + worker eligibility; no Redis)."""

from __future__ import annotations

import unittest
import uuid
from typing import Optional
from unittest.mock import MagicMock, patch

from app.models.document import Document
from app.services.document_reprocess import (
    ReprocessDocumentBadRequest,
    prepare_document_for_pipeline_reprocess,
    reprocess_document_for_organization,
)


def _sample_document(
    *,
    status: str,
    sha256: Optional[str] = "a" * 64,
    byte_size: Optional[int] = 100,
) -> Document:
    """Minimal ``Document`` for status / hash checks (no DB)."""
    oid = uuid.uuid4()
    return Document(
        id=uuid.uuid4(),
        organization_id=oid,
        site_id=None,
        bucket="test-bucket",
        object_key=f"{oid}/doc",
        sha256=sha256,
        mime_type="application/pdf",
        byte_size=byte_size,
        source="upload",
        processing_status=status,
        processing_error="previous failure" if status == "failed" else None,
    )


class TestPrepareDocumentForPipelineReprocess(unittest.TestCase):
    def test_extracted_becomes_queued_and_clears_error(self) -> None:
        doc = _sample_document(status="extracted")
        doc.processing_error = "should clear"
        session = MagicMock()
        prepare_document_for_pipeline_reprocess(session, document=doc)
        self.assertEqual(doc.processing_status, "queued")
        self.assertIsNone(doc.processing_error)
        session.flush.assert_called_once()

    def test_failed_is_reprocessable(self) -> None:
        doc = _sample_document(status="failed")
        session = MagicMock()
        prepare_document_for_pipeline_reprocess(session, document=doc)
        self.assertEqual(doc.processing_status, "queued")
        self.assertIsNone(doc.processing_error)

    def test_received_is_reprocessable(self) -> None:
        doc = _sample_document(status="received")
        session = MagicMock()
        prepare_document_for_pipeline_reprocess(session, document=doc)
        self.assertEqual(doc.processing_status, "queued")

    def test_queued_clears_error_and_stays_requeueable(self) -> None:
        doc = _sample_document(status="queued")
        doc.processing_error = "stale"
        session = MagicMock()
        prepare_document_for_pipeline_reprocess(session, document=doc)
        self.assertEqual(doc.processing_status, "queued")
        self.assertIsNone(doc.processing_error)

    def test_pending_clears_error(self) -> None:
        doc = _sample_document(status="pending")
        session = MagicMock()
        prepare_document_for_pipeline_reprocess(session, document=doc)
        self.assertEqual(doc.processing_status, "queued")

    def test_awaiting_object_raises_bad_request(self) -> None:
        doc = _sample_document(status="awaiting_object", sha256=None, byte_size=None)
        session = MagicMock()
        with self.assertRaises(ReprocessDocumentBadRequest):
            prepare_document_for_pipeline_reprocess(session, document=doc)

    def test_unknown_status_raises_bad_request(self) -> None:
        doc = _sample_document(status="weird")
        session = MagicMock()
        with self.assertRaises(ReprocessDocumentBadRequest) as ctx:
            prepare_document_for_pipeline_reprocess(session, document=doc)
        self.assertIn("weird", str(ctx.exception))

    def test_missing_sha_raises_bad_request(self) -> None:
        doc = _sample_document(status="extracted", sha256=None, byte_size=1)
        session = MagicMock()
        with self.assertRaises(ReprocessDocumentBadRequest):
            prepare_document_for_pipeline_reprocess(session, document=doc)


class TestReprocessDocumentForOrganization(unittest.TestCase):
    def test_returns_none_when_document_missing(self) -> None:
        session = MagicMock()
        org = uuid.uuid4()
        did = uuid.uuid4()
        with patch(
            "app.services.document_reprocess.get_document_for_organization",
            return_value=None,
        ):
            out = reprocess_document_for_organization(session, organization_id=org, document_id=did)
        self.assertIsNone(out)

    def test_returns_document_when_found(self) -> None:
        doc = _sample_document(status="extracted")
        session = MagicMock()
        org = doc.organization_id
        with patch(
            "app.services.document_reprocess.get_document_for_organization",
            return_value=doc,
        ):
            out = reprocess_document_for_organization(session, organization_id=org, document_id=doc.id)
        self.assertIs(out, doc)
        self.assertEqual(out.processing_status, "queued")
