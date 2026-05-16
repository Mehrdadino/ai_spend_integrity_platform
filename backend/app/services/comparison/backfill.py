"""§3e comparison backfill: re-run §3b/§3d after bills change without opening the viewer.

When a normalized bill lands (worker) or a site assignment changes prior chains, persisted
``anomalies`` must be recomputed so the inbox matches ``GET …/bill/comparison`` outcomes.

**Site chain rule:** bills on the same ``site_id`` are ordered newest-first (see ``period``).
After upserting the bill for document *D*, we re-run comparison for a prefix of that ordering
through *D* and—when *D* is the **newest** row—also the **next** bill, because its immediate
prior shifts when a new bill lands above it.

**Session handling:** each ``evaluate_document_comparison`` is followed by ``commit()`` so the
ORM does not keep stale ``Anomaly`` rows across SQL ``DELETE`` + re-insert (avoids spurious
``UPDATE anomalies SET bill_id = NULL`` flushes).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.config import get_settings
from app.repositories.bills import (
    get_bill_for_org_document,
    iter_document_ids_for_site_keyset,
    list_document_ids_newest_through_anchor,
)
from app.services.comparison.evaluate import evaluate_document_comparison
from app.services.comparison.limits import DEFAULT_SITE_REFRESH_MAX_BILLS

logger = logging.getLogger(__name__)


def document_ids_newest_through_anchor(
    ordered_document_ids_newest_first: Sequence[uuid.UUID],
    anchor_document_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Return document IDs that need §3d refresh relative to ``anchor_document_id``.

    ``ordered_document_ids_newest_first`` matches ``list_bills_for_site`` (newest index 0).

    We include indices ``0 .. idx`` where ``idx`` is the anchor's index (the trigger bill and
    every strictly newer bill—none—plus the anchor). When the anchor is the **newest** bill
    (``idx == 0``) and another bill exists at index 1, we extend through index **1**: the
    former newest bill's "prior" changed from its old neighbor to this new top row.

    If the anchor is missing from the list (scan truncation), return only the anchor ID so
    callers still run one evaluation.
    """
    ids = list(ordered_document_ids_newest_first)
    try:
        idx = ids.index(anchor_document_id)
    except ValueError:
        return [anchor_document_id]

    if idx == 0 and len(ids) > 1:
        return list(ids[:2])
    return list(ids[: idx + 1])


def run_document_comparison_backfill(
    session: Session,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    site_bill_scan_limit: int | None = None,
) -> list[uuid.UUID]:
    """Recompute §3d anomalies for the anchor document and any needed same-site neighbors.

    Returns the list of ``document_id`` values evaluated. **Commits once per document** so RQ /
    long chains do not accumulate orphan ORM state (required for correct anomaly DELETE/INSERT).

    Callers should not wrap this in an outer transaction that expects a single commit at the end.
    """
    current = get_bill_for_org_document(
        session,
        organization_id=organization_id,
        document_id=document_id,
    )
    if current is None:
        return []

    if current.site_id is None:
        evaluate_document_comparison(
            session,
            organization_id=organization_id,
            document_id=document_id,
        )
        session.commit()
        return [document_id]

    # Indexed SQL: only bills whose prior chain may have changed (not capped at 500/2000).
    _ = site_bill_scan_limit  # legacy RQ kwarg; ignored since §3e scale SQL path.
    targets = list_document_ids_newest_through_anchor(
        session,
        organization_id=organization_id,
        anchor=current,
    )

    touched: list[uuid.UUID] = []
    for doc_id in targets:
        evaluate_document_comparison(
            session,
            organization_id=organization_id,
            document_id=doc_id,
        )
        session.commit()
        touched.append(doc_id)
    return touched


def run_site_wide_comparison_refresh(
    session: Session,
    *,
    organization_id: uuid.UUID,
    site_id: uuid.UUID,
    site_bill_scan_limit: int | None = None,
) -> list[uuid.UUID]:
    """Re-run comparison for every bill on this site (repair after a bill moved away).

    Uses keyset pages so sites with >2000 bills are not truncated. Commits after each document.
    """
    _ = site_bill_scan_limit  # legacy RQ kwarg
    settings = get_settings()
    max_bills = settings.site_bill_refresh_max_bills
    if max_bills < 0:
        max_bills = DEFAULT_SITE_REFRESH_MAX_BILLS
    page_size = max(1, settings.site_bill_keyset_page_size)
    touched: list[uuid.UUID] = []
    for doc_id in iter_document_ids_for_site_keyset(
        session,
        organization_id=organization_id,
        site_id=site_id,
        page_size=page_size,
        max_bills=max_bills,
    ):
        evaluate_document_comparison(
            session,
            organization_id=organization_id,
            document_id=doc_id,
        )
        session.commit()
        touched.append(doc_id)
    if max_bills > 0 and len(touched) >= max_bills:
        logger.warning(
            "comparison site refresh: hit max_bills=%s for site=%s org=%s",
            max_bills,
            site_id,
            organization_id,
        )
    return touched
