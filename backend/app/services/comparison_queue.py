"""Enqueue §3e comparison backfill (separate small RQ jobs on the ``documents`` queue).

After the document worker materializes a bill, we queue ``run_document_comparison_backfill_job``
so ``anomalies`` rows exist without calling ``GET …/bill/comparison``. Site reassignment and
document soft-delete may queue a **site-wide refresh** so remaining bills get priors that skip
removed or reassigned neighbors.
"""

from __future__ import annotations

import logging
import uuid

from redis import Redis
from rq import Queue

from app.config import get_settings
from app.jobs.comparison_jobs import (
    run_document_comparison_backfill_job,
    run_site_comparison_refresh_job,
)

logger = logging.getLogger(__name__)


def enqueue_document_comparison_backfill(document_id: uuid.UUID) -> None:
    """Enqueue comparison backfill; no-op if ``redis_url`` is empty."""
    settings = get_settings()
    if not (settings.redis_url or "").strip():
        logger.warning(
            "comparison_queue: redis_url unset; comparison backfill not enqueued document=%s",
            document_id,
        )
        return
    conn = Redis.from_url(settings.redis_url)
    queue = Queue("documents", connection=conn)
    queue.enqueue(run_document_comparison_backfill_job, str(document_id))
    logger.info("comparison_queue: enqueued comparison backfill document=%s", document_id)


def enqueue_document_comparison_backfill_safe(document_id: uuid.UUID) -> None:
    """Like ``enqueue_document_comparison_backfill`` but swallows Redis errors."""
    try:
        enqueue_document_comparison_backfill(document_id)
    except Exception:
        logger.exception(
            "comparison_queue: enqueue backfill failed document=%s",
            document_id,
        )


def enqueue_site_comparison_refresh(organization_id: uuid.UUID, site_id: uuid.UUID) -> None:
    """Enqueue a full-site comparison refresh (bounded bill scan per ``list_bills_for_site``)."""
    settings = get_settings()
    if not (settings.redis_url or "").strip():
        logger.warning(
            "comparison_queue: redis_url unset; site refresh not enqueued org=%s site=%s",
            organization_id,
            site_id,
        )
        return
    conn = Redis.from_url(settings.redis_url)
    queue = Queue("documents", connection=conn)
    queue.enqueue(
        run_site_comparison_refresh_job,
        str(organization_id),
        str(site_id),
    )
    logger.info(
        "comparison_queue: enqueued site comparison refresh org=%s site=%s",
        organization_id,
        site_id,
    )


def enqueue_site_comparison_refresh_safe(organization_id: uuid.UUID, site_id: uuid.UUID) -> None:
    try:
        enqueue_site_comparison_refresh(organization_id, site_id)
    except Exception:
        logger.exception(
            "comparison_queue: enqueue site refresh failed org=%s site=%s",
            organization_id,
            site_id,
        )


def enqueue_comparison_refresh_after_document_soft_delete(
    organization_id: uuid.UUID,
    site_id: uuid.UUID | None,
) -> None:
    """§3e: after soft delete, recompute anomalies for bills still on ``site_id``.

    The deleted document's rows are hidden from the inbox; neighbors may still reference it as
    a prior until comparison runs again with ``Document.deleted_at IS NULL`` filters.
    """
    if site_id is None:
        return
    enqueue_site_comparison_refresh_safe(organization_id, site_id)
