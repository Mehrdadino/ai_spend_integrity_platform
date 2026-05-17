"""Document display_name normalization and repository update."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import MagicMock

from app.models.document import Document
from app.repositories.documents import update_document_display_name_for_organization
from app.schemas.document_display_name import normalize_display_name


class TestDocumentDisplayName(unittest.TestCase):
    def test_normalize_blank_to_none(self) -> None:
        self.assertIsNone(normalize_display_name(None))
        self.assertIsNone(normalize_display_name(""))
        self.assertIsNone(normalize_display_name("   "))

    def test_normalize_strips(self) -> None:
        self.assertEqual(normalize_display_name("  March bill  "), "March bill")

    def test_update_clears_name(self) -> None:
        doc = Document(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            bucket="b",
            object_key="k",
            mime_type="application/pdf",
            source="upload",
            processing_status="extracted",
            display_name="Old",
        )
        session = MagicMock()
        session.scalar.return_value = doc
        out = update_document_display_name_for_organization(
            session,
            document_id=doc.id,
            organization_id=doc.organization_id,
            display_name=None,
        )
        self.assertIs(out, doc)
        self.assertIsNone(doc.display_name)


if __name__ == "__main__":
    unittest.main()
