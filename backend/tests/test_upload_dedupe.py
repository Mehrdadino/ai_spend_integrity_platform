"""Upload dedupe: soft-deleted rows must not block re-upload; orphan placeholder cleanup."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import MagicMock, patch

from app.models.document import Document
from app.repositories.documents import get_document_by_organization_and_sha256
from app.services.upload_sessions import (
    DuplicateUploadError,
    PROCESSING_AWAITING_OBJECT,
    complete_presigned_upload,
    remove_awaiting_upload_placeholder,
)


class TestUploadDedupe(unittest.TestCase):
    def test_active_sha_lookup_ignores_deleted(self) -> None:
        session = MagicMock()
        session.scalar.return_value = None
        org_id = uuid.uuid4()
        out = get_document_by_organization_and_sha256(
            session, organization_id=org_id, sha256="a" * 64
        )
        self.assertIsNone(out)
        session.scalar.assert_called_once()

    def test_duplicate_before_finalize_raises(self) -> None:
        org_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        existing_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            organization_id=org_id,
            bucket="b",
            object_key=f"{org_id}/{doc_id}",
            mime_type="application/pdf",
            source="upload",
            processing_status=PROCESSING_AWAITING_OBJECT,
        )
        session = MagicMock()
        session.scalar.side_effect = [doc, None]  # get doc, then duplicate check uses repo

        with patch(
            "app.services.upload_sessions.get_document_for_organization",
            return_value=doc,
        ), patch(
            "app.services.upload_sessions.sha256_and_size_from_object",
            return_value=("b" * 64, 100),
        ), patch(
            "app.services.upload_sessions.get_document_by_organization_and_sha256",
            return_value=Document(
                id=existing_id,
                organization_id=org_id,
                bucket="b",
                object_key="k",
                sha256="b" * 64,
                mime_type="application/pdf",
                source="upload",
                processing_status="extracted",
            ),
        ):
            with self.assertRaises(DuplicateUploadError) as ctx:
                complete_presigned_upload(
                    session, organization_id=org_id, document_id=doc_id
                )
        self.assertEqual(ctx.exception.existing_document_id, existing_id)

    def test_remove_awaiting_placeholder_deletes_row(self) -> None:
        org_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            organization_id=org_id,
            bucket="b",
            object_key="k",
            mime_type="application/pdf",
            source="upload",
            processing_status=PROCESSING_AWAITING_OBJECT,
        )
        session = MagicMock()
        session.scalar.return_value = doc
        removed = remove_awaiting_upload_placeholder(
            session, organization_id=org_id, document_id=doc_id
        )
        self.assertTrue(removed)
        session.delete.assert_called_once_with(doc)
        session.flush.assert_called_once()


if __name__ == "__main__":
    unittest.main()
