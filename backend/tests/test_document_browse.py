"""Paginated document browse/search (repository)."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import MagicMock

from app.repositories.documents import browse_documents_for_organization


class TestDocumentBrowse(unittest.TestCase):
    def test_returns_rows_and_total(self) -> None:
        org_id = uuid.uuid4()
        doc = MagicMock()
        session = MagicMock()
        session.scalar.return_value = 42
        session.scalars.return_value.all.return_value = [doc]

        rows, total = browse_documents_for_organization(
            session,
            organization_id=org_id,
            q="march",
            offset=20,
            limit=20,
        )
        self.assertEqual(rows, [doc])
        self.assertEqual(total, 42)
        self.assertEqual(session.scalar.call_count, 1)
        self.assertEqual(session.scalars.call_count, 1)


if __name__ == "__main__":
    unittest.main()
