"""Orchestrate §3c peer comparison for an org-scoped document (loads peers, persists §3d)."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.repositories.bills import (
    get_bill_for_org_document,
    list_peer_bill_candidates_for_anchor,
)
from app.schemas.comparison import DocumentComparisonResponse
from app.services.comparison.peer_config import PEER_RULE_PACK_VERSION
from app.services.comparison.peer_pack_v1 import evaluate_peer_pack_v1
from app.services.comparison.peer_slice import period_window_for_anchor
from app.services.comparison.peer_sites import (
    normalize_user_peer_site_ids,
    save_peer_site_ids_to_bill,
)
from app.services.comparison.persist_anomalies import replace_anomalies_for_comparison


def evaluate_document_peer_comparison(
    session: Session,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    peer_site_ids: list[uuid.UUID] | None = None,
) -> DocumentComparisonResponse:
    """Run §3c peer pack for the document's bill; persist under ``comparison-peer-v1``.

    Intended for batch materialize / pilot refresh — not the default worker hot path.
    """
    current = get_bill_for_org_document(
        session,
        organization_id=organization_id,
        document_id=document_id,
    )
    if current is None:
        return DocumentComparisonResponse(
            document_id=document_id,
            bill_id=None,
            site_id=None,
            rule_pack_version=PEER_RULE_PACK_VERSION,
            compared_to_bill_id=None,
            compared_to_period_end=None,
            findings=[],
        )

    bill_pk = current.id
    site_pk = current.site_id

    _, _, window_start, window_end = period_window_for_anchor(current)
    user_peer_ids: list[uuid.UUID] | None = None
    sql_peer_filter: list[uuid.UUID] | None = None
    if peer_site_ids is not None:
        user_peer_ids = normalize_user_peer_site_ids(current, peer_site_ids)
        sql_peer_filter = user_peer_ids
        save_peer_site_ids_to_bill(current, user_peer_ids)

    candidates = list_peer_bill_candidates_for_anchor(
        session,
        organization_id=organization_id,
        anchor=current,
        window_start=window_start,
        window_end=window_end,
        peer_site_ids=sql_peer_filter,
    )
    findings = evaluate_peer_pack_v1(
        anchor=current,
        peer_candidates=candidates,
        user_selected_peer_site_ids=user_peer_ids,
    )

    # Skip ``acquire_site_comparison_lock``: §3c uses ``comparison-peer-v1`` fingerprints
    # distinct from §3b site MoM rows. Holding the per-site lock here blocked for minutes when
    # an RQ site-wide backfill was already running on the same site.

    replace_anomalies_for_comparison(
        session,
        current=current,
        compared_to_bill_id=None,
        findings=findings,
        rule_pack_version=PEER_RULE_PACK_VERSION,
    )

    return DocumentComparisonResponse(
        document_id=document_id,
        bill_id=bill_pk,
        site_id=site_pk,
        rule_pack_version=PEER_RULE_PACK_VERSION,
        compared_to_bill_id=None,
        compared_to_period_end=current.period_end,
        findings=findings,
        peer_site_ids_used=user_peer_ids or [],
    )
