"""RQ jobs for §3e comparison backfill (runs after bill materialization or site changes).

Individual RQ handlers rely on ``run_document_comparison_backfill`` /
``run_site_wide_comparison_refresh`` to **commit per document** so SQLAlchemy state stays
aligned with §3d anomaly persistence under repeated comparisons.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.db.session import get_session_factory
from app.models.document import Document
from app.services.comparison.backfill import (
    run_document_comparison_backfill,
    run_site_wide_comparison_refresh,
)

logger = logging.getLogger(__name__)


def run_document_comparison_backfill_job(document_id: str) -> None:
    """Queue worker entrypoint: refresh anomalies for one document (and same-site chain)."""
    oid = uuid.UUID(document_id)
    factory = get_session_factory()
    session: Session = factory()
    try:
        doc = session.get(Document, oid)
        if doc is None or doc.deleted_at is not None:
            logger.warning("comparison_jobs: skip backfill, document missing id=%s", document_id)
            return
        touched = run_document_comparison_backfill(
            session,
            organization_id=doc.organization_id,
            document_id=oid,
        )
        # ``run_document_comparison_backfill`` issues a commit per document; no final batch.
        logger.info(
            "comparison_jobs: backfill document=%s org=%s touched=%s",
            document_id,
            doc.organization_id,
            len(touched),
        )
    except Exception:
        session.rollback()
        logger.exception("comparison_jobs: backfill failed document=%s", document_id)
        raise
    finally:
        session.close()


def run_site_comparison_refresh_job(organization_id: str, site_id: str) -> None:
    """Re-evaluate comparison for all bills still on ``site_id`` (e.g. after a bill reassigned)."""
    org_uuid = uuid.UUID(organization_id)
    site_uuid = uuid.UUID(site_id)
    factory = get_session_factory()
    session: Session = factory()
    try:
        n = run_site_wide_comparison_refresh(session, organization_id=org_uuid, site_id=site_uuid)
        # Each evaluation commits inside ``run_site_wide_comparison_refresh``.
        logger.info(
            "comparison_jobs: site refresh org=%s site=%s documents=%s",
            organization_id,
            site_id,
            len(n),
        )
    except Exception:
        session.rollback()
        logger.exception(
            "comparison_jobs: site refresh failed org=%s site=%s",
            organization_id,
            site_id,
        )
        raise
    finally:
        session.close()
