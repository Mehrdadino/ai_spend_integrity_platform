"""Batch comparison materialization for the anomaly inbox (§3d without opening each document).

The Anomalies tab **Refresh** action calls ``POST /anomalies/materialize-comparisons``, which
reuses ``evaluate_document_comparison`` (same as ``GET …/bill/comparison``) for every
``extracted`` document that already has a ``bills`` row. Each document is committed in its
own transaction so one failure does not roll back the rest.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.repositories.documents import list_extracted_document_ids_with_bills
from app.services.comparison.evaluate import evaluate_document_comparison
from app.services.comparison.limits import DEFAULT_SITE_BILL_SCAN

logger = logging.getLogger(__name__)


def materialize_comparisons_for_organization(
    session: Session,
    *,
    organization_id: uuid.UUID,
    site_id: Optional[uuid.UUID] = None,
    limit: int = DEFAULT_SITE_BILL_SCAN,
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """Run §3b/§3d for eligible documents; return ``(succeeded_ids, failed_ids)``."""
    doc_ids = list_extracted_document_ids_with_bills(
        session,
        organization_id=organization_id,
        site_id=site_id,
        limit=limit,
    )
    ok: list[uuid.UUID] = []
    failed: list[uuid.UUID] = []
    for doc_id in doc_ids:
        try:
            evaluate_document_comparison(
                session,
                organization_id=organization_id,
                document_id=doc_id,
            )
            session.commit()
            ok.append(doc_id)
        except Exception:
            session.rollback()
            logger.exception(
                "materialize_comparisons: failed document_id=%s org=%s",
                doc_id,
                organization_id,
            )
            failed.append(doc_id)
    return ok, failed
