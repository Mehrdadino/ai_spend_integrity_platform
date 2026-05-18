"""§3e: document backfill delegates to bounded site-wide refresh when a site is set."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import MagicMock, patch

from app.services.comparison.backfill import run_document_comparison_backfill


class TestDocumentBackfillUsesSiteWide(unittest.TestCase):
    @patch("app.services.comparison.backfill.run_site_wide_comparison_refresh")
    @patch("app.services.comparison.backfill.get_bill_for_org_document")
    def test_site_bill_triggers_site_wide_refresh(
        self,
        mock_get_bill: MagicMock,
        mock_site_refresh: MagicMock,
    ) -> None:
        org_id = uuid.uuid4()
        site_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        bill = MagicMock()
        bill.site_id = site_id
        bill.document_id = doc_id
        mock_get_bill.return_value = bill
        mock_site_refresh.return_value = [doc_id]

        session = MagicMock()
        touched = run_document_comparison_backfill(
            session, organization_id=org_id, document_id=doc_id
        )

        mock_site_refresh.assert_called_once_with(
            session, organization_id=org_id, site_id=site_id
        )
        self.assertEqual(touched, [doc_id])

    @patch("app.services.comparison.backfill.evaluate_document_comparison")
    @patch("app.services.comparison.backfill.get_bill_for_org_document")
    def test_no_site_evaluates_single_document(
        self,
        mock_get_bill: MagicMock,
        mock_eval: MagicMock,
    ) -> None:
        org_id = uuid.uuid4()
        doc_id = uuid.uuid4()
        bill = MagicMock()
        bill.site_id = None
        mock_get_bill.return_value = bill

        session = MagicMock()
        touched = run_document_comparison_backfill(
            session, organization_id=org_id, document_id=doc_id
        )

        mock_eval.assert_called_once()
        session.commit.assert_called_once()
        self.assertEqual(touched, [doc_id])


if __name__ == "__main__":
    unittest.main()
