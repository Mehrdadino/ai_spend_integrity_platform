"""Soft delete documents (repository; no DB)."""

from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.models.document import Document
from app.repositories.documents import soft_delete_document_for_organization


class TestSoftDeleteDocument(unittest.TestCase):
    def test_sets_deleted_at(self) -> None:
        org_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            organization_id=org_id,
            bucket="b",
            object_key="k",
            mime_type="application/pdf",
            source="upload",
            processing_status="extracted",
        )
        session = MagicMock()
        session.scalar.return_value = doc
        out = soft_delete_document_for_organization(
            session, document_id=doc_id, organization_id=org_id
        )
        self.assertIs(out, doc)
        self.assertIsNotNone(doc.deleted_at)
        session.flush.assert_called_once()

    def test_returns_none_when_missing(self) -> None:
        session = MagicMock()
        session.scalar.return_value = None
        out = soft_delete_document_for_organization(
            session,
            document_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
        )
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()
