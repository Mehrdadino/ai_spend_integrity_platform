"""Orchestrate §3b comparison for an org-scoped document (loads bills, runs rule pack, persists §3d)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.repositories.bills import get_prior_bills_for_org_document
from app.schemas.comparison import DocumentComparisonResponse
from app.services.comparison.locking import acquire_site_comparison_lock
from app.services.comparison.period import effective_period_end
from app.services.comparison.persist_anomalies import replace_anomalies_for_comparison
from app.services.comparison.rule_pack_v1 import evaluate_rule_pack_v1
from app.services.comparison.rules_config import RULE_PACK_VERSION


def evaluate_document_comparison(
    session: Session,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
) -> DocumentComparisonResponse:
    """Return rule-pack findings for the document's current bill (empty when no bill row).

    When a normalized bill exists, §3d rows for ``RULE_PACK_VERSION`` are replaced for that bill so
    the inbox stays aligned with the latest comparison run (typically via ``GET …/bill/comparison``).

    Bill PKs are copied before the anomaly replace + flush so the response does not rely on an
    ORM instance that may be expired after persistence.
    """
    current, priors = get_prior_bills_for_org_document(
        session,
        organization_id=organization_id,
        document_id=document_id,
        limit=1,
    )
    if current is None:
        return DocumentComparisonResponse(
            document_id=document_id,
            bill_id=None,
            site_id=None,
            rule_pack_version=RULE_PACK_VERSION,
            compared_to_bill_id=None,
            compared_to_period_end=None,
            findings=[],
        )

    # Snapshot ids before §3d replace + flush so we never read a potentially expired ``Bill``.
    bill_pk = current.id
    site_pk = current.site_id

    findings, compared_id = evaluate_rule_pack_v1(current=current, priors=priors)
    compared_period = None
    if compared_id is not None and priors:
        compared_period = effective_period_end(priors[0])

    if current.site_id is not None:
        acquire_site_comparison_lock(session, site_id=current.site_id)

    replace_anomalies_for_comparison(
        session,
        current=current,
        compared_to_bill_id=compared_id,
        findings=findings,
        rule_pack_version=RULE_PACK_VERSION,
    )

    return DocumentComparisonResponse(
        document_id=document_id,
        bill_id=bill_pk,
        site_id=site_pk,
        rule_pack_version=RULE_PACK_VERSION,
        compared_to_bill_id=compared_id,
        compared_to_period_end=compared_period,
        findings=findings,
    )
