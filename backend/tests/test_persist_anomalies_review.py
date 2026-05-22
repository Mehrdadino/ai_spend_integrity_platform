"""§3d replace must preserve §5 review_status when comparison re-runs (same fingerprint)."""

from __future__ import annotations

import unittest
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from app.models.anomaly import Anomaly
from app.models.bill import Bill
from app.schemas.comparison import ComparisonFindingResponse
from app.services.comparison.persist_anomalies import replace_anomalies_for_comparison
from app.services.comparison.rules_config import RULE_PACK_VERSION


def _bill() -> Bill:
    return Bill(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        site_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        spend_domain="utility",
        currency="USD",
        normalization_version="norm-v1",
        period_end=date(2026, 3, 31),
        created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        total_amount=Decimal("100.00"),
        line_items=[],
    )


class TestPersistAnomaliesReviewPreserve(unittest.TestCase):
    def test_replace_keeps_review_status_for_matching_fingerprint(self) -> None:
        bill = _bill()
        fp = "mom_total_change|none|" + str(bill.id)
        existing_id = uuid.uuid4()
        existing = Anomaly(
            id=existing_id,
            organization_id=bill.organization_id,
            site_id=bill.site_id,
            document_id=bill.document_id,
            bill_id=bill.id,
            rule_pack_version=RULE_PACK_VERSION,
            rule_id="mom_total_change",
            period_end=date(2026, 3, 31),
            fingerprint=fp,
            severity="warning",
            title="Old title",
            summary="Old summary",
            evidence={"pct_change": 15},
            review_status="approved",
        )

        session = MagicMock()
        session.scalars.return_value.all.return_value = [existing]

        findings = [
            ComparisonFindingResponse(
                rule_id="mom_total_change",
                severity="critical",
                title="New title",
                summary="New summary",
                evidence={"pct_change": 25},
            )
        ]
        replace_anomalies_for_comparison(
            session,
            current=bill,
            compared_to_bill_id=None,
            findings=findings,
            rule_pack_version=RULE_PACK_VERSION,
        )

        self.assertEqual(existing.review_status, "approved")
        self.assertEqual(existing.id, existing_id)
        self.assertEqual(existing.severity, "critical")
        self.assertEqual(existing.title, "New title")
        session.add.assert_not_called()
        session.delete.assert_not_called()
        session.flush.assert_called_once()

    def test_replace_deletes_other_rule_pack_before_insert(self) -> None:
        """Site unique index omits rule_pack_version; stale rows must not block new pack."""
        bill = _bill()
        fp = "no_prior_bill|none|" + str(bill.id)
        old_pack_row = Anomaly(
            id=uuid.uuid4(),
            organization_id=bill.organization_id,
            site_id=bill.site_id,
            document_id=bill.document_id,
            bill_id=bill.id,
            rule_pack_version="comparison-v1.2",
            rule_id="no_prior_bill",
            period_end=date(2026, 3, 31),
            fingerprint=fp,
            severity="info",
            title="Old pack",
            summary="Old",
            evidence={},
            review_status="open",
        )

        session = MagicMock()
        session.scalars.return_value.all.return_value = [old_pack_row]

        findings = [
            ComparisonFindingResponse(
                rule_id="no_prior_bill",
                severity="info",
                title="First bill at this site (baseline)",
                summary="Baseline",
                evidence={},
            )
        ]
        replace_anomalies_for_comparison(
            session,
            current=bill,
            compared_to_bill_id=None,
            findings=findings,
            rule_pack_version=RULE_PACK_VERSION,
        )

        session.delete.assert_called_once_with(old_pack_row)
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        self.assertEqual(added.rule_pack_version, RULE_PACK_VERSION)
        self.assertEqual(added.fingerprint, fp)

    def test_replace_keeps_other_pack_family(self) -> None:
        """§3c peer rows must survive a §3b site-pack rerun."""
        bill = _bill()
        peer_row = Anomaly(
            id=uuid.uuid4(),
            organization_id=bill.organization_id,
            site_id=bill.site_id,
            document_id=bill.document_id,
            bill_id=bill.id,
            rule_pack_version="comparison-peer-v1",
            rule_id="peer_fee_line_rare",
            period_end=date(2026, 3, 31),
            fingerprint="peer_fee_line_rare|none|" + str(bill.id) + "|fee|x",
            severity="warning",
            title="Peer",
            summary="Peer",
            evidence={},
            review_status="open",
        )
        session = MagicMock()
        session.scalars.return_value.all.return_value = [peer_row]
        replace_anomalies_for_comparison(
            session,
            current=bill,
            compared_to_bill_id=None,
            findings=[
                ComparisonFindingResponse(
                    rule_id="no_prior_bill",
                    severity="info",
                    title="First bill",
                    summary="Baseline",
                    evidence={},
                )
            ],
            rule_pack_version=RULE_PACK_VERSION,
        )
        session.delete.assert_not_called()
        session.add.assert_called_once()


if __name__ == "__main__":
    unittest.main()
