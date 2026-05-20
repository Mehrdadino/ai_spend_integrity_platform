"""Push document IDs to the Redis/RQ queue after Postgres commit (step 1d).

Separated from FastAPI routes so the CLI and HTTP layer can share the same
enqueue path. Failures are logged but do not crash the API response path.
"""

from __future__ import annotations

import logging
import uuid

from app.config import get_settings
from app.jobs.document_jobs import process_document_pipeline
from app.services.rq_enqueue import enqueue_documents_job

logger = logging.getLogger(__name__)


def enqueue_document_pipeline(document_id: uuid.UUID) -> None:
    """Enqueue ``process_document_pipeline``; no-op if ``redis_url`` is empty."""
    settings = get_settings()
    if not (settings.redis_url or "").strip():
        logger.warning(
            "document_pipeline_queue: redis_url unset; document %s not enqueued",
            document_id,
        )
        return
    enqueue_documents_job(
        process_document_pipeline,
        str(document_id),
        job_timeout_seconds=settings.rq_document_job_timeout_seconds,
        description="document_pipeline",
    )
    logger.info("document_pipeline_queue: enqueued document %s", document_id)


def enqueue_document_pipeline_safe(document_id: uuid.UUID) -> None:
    """Like ``enqueue_document_pipeline`` but swallows errors (e.g. Redis down)."""
    try:
        enqueue_document_pipeline(document_id)
    except Exception:
        logger.exception(
            "document_pipeline_queue: enqueue failed for %s (document may stay queued)",
            document_id,
        )
