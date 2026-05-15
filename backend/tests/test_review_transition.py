"""§5a transition rules (unit tests; no database)."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import MagicMock

from app.models.anomaly import Anomaly
from app.services.review.transition import ReviewTransitionError, apply_review_transition


def _minimal_anomaly(*, status: str = "open") -> Anomaly:
    return Anomaly(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        site_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        bill_id=uuid.uuid4(),
        rule_pack_version="comparison-v1",
        rule_id="mom_total_change",
        fingerprint="x|y|z",
        severity="warning",
        title="t",
        summary="s",
        evidence={},
        review_status=status,
    )


class TestReviewTransitions(unittest.TestCase):
    def test_open_to_approved(self) -> None:
        a = _minimal_anomaly(status="open")
        session = MagicMock()
        apply_review_transition(session, anomaly=a, to_status="approved")
        self.assertEqual(a.review_status, "approved")
        session.add.assert_called_once()
        session.flush.assert_called_once()

    def test_rejects_invalid_transition(self) -> None:
        a = _minimal_anomaly(status="approved")
        session = MagicMock()
        with self.assertRaises(ReviewTransitionError):
            apply_review_transition(session, anomaly=a, to_status="dismissed")

    def test_reopen_from_dismissed(self) -> None:
        a = _minimal_anomaly(status="dismissed")
        session = MagicMock()
        apply_review_transition(session, anomaly=a, to_status="open")
        self.assertEqual(a.review_status, "open")


if __name__ == "__main__":
    unittest.main()
