"""Shared RQ enqueue helpers (job timeouts, connection).

RQ defaults to **180s** per job if ``job_timeout`` is omitted — too low for OCR + LLM +
comparison backfill on dev hardware. Always pass explicit timeouts from ``Settings``.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from redis import Redis
from rq import Queue

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def redis_connection(settings: Settings | None = None) -> Redis:
    """Build a Redis client from app settings."""
    cfg = settings or get_settings()
    return Redis.from_url(cfg.redis_url)


def documents_queue(settings: Settings | None = None) -> Queue:
    """RQ queue used by document pipeline and §3e comparison jobs."""
    cfg = settings or get_settings()
    return Queue("documents", connection=redis_connection(cfg))


def enqueue_documents_job(
    func: Callable[..., Any],
    *args: Any,
    job_timeout_seconds: int,
    description: str = "",
) -> None:
    """Enqueue on ``documents`` with an explicit timeout (seconds)."""
    queue = documents_queue()
    job = queue.enqueue(func, *args, job_timeout=job_timeout_seconds)
    logger.info(
        "rq_enqueue: %s job_id=%s timeout=%ss args=%s",
        description or func.__name__,
        job.id,
        job_timeout_seconds,
        args,
    )
