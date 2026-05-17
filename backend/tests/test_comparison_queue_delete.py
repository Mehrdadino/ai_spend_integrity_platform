"""§3e enqueue after document soft-delete."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

from app.services.comparison_queue import enqueue_comparison_refresh_after_document_soft_delete


class TestComparisonQueueAfterDelete(unittest.TestCase):
    @patch("app.services.comparison_queue.enqueue_site_comparison_refresh_safe")
    def test_skips_when_no_site(self, mock_refresh: unittest.mock.MagicMock) -> None:
        enqueue_comparison_refresh_after_document_soft_delete(uuid.uuid4(), None)
        mock_refresh.assert_not_called()

    @patch("app.services.comparison_queue.enqueue_site_comparison_refresh_safe")
    def test_enqueues_site_refresh(self, mock_refresh: unittest.mock.MagicMock) -> None:
        org_id = uuid.uuid4()
        site_id = uuid.uuid4()
        enqueue_comparison_refresh_after_document_soft_delete(org_id, site_id)
        mock_refresh.assert_called_once_with(org_id, site_id)


if __name__ == "__main__":
    unittest.main()
