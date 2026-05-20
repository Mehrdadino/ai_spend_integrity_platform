"""RQ enqueue passes explicit job_timeout (not RQ's 180s default)."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import MagicMock, patch

from app.services.document_pipeline_queue import enqueue_document_pipeline


class TestRqEnqueue(unittest.TestCase):
    @patch("app.services.document_pipeline_queue.enqueue_documents_job")
    @patch("app.services.document_pipeline_queue.get_settings")
    def test_document_pipeline_uses_configured_timeout(
        self,
        mock_settings: MagicMock,
        mock_enqueue: MagicMock,
    ) -> None:
        mock_settings.return_value.redis_url = "redis://127.0.0.1:6379/0"
        mock_settings.return_value.rq_document_job_timeout_seconds = 600
        doc_id = uuid.uuid4()
        enqueue_document_pipeline(doc_id)
        mock_enqueue.assert_called_once()
        _args, kwargs = mock_enqueue.call_args
        self.assertEqual(kwargs["job_timeout_seconds"], 600)
        self.assertEqual(_args[1], str(doc_id))


if __name__ == "__main__":
    unittest.main()
