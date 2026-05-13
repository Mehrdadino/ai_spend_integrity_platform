"""CLI: run one RQ worker process for the ``documents`` queue (step 1d).

Start Redis (e.g. ``docker compose up -d redis``), then from ``backend/``::

  document-worker

RQ **2.x** removed ``rq.Connection``; pass ``connection=`` into ``Worker`` instead.

**macOS (Darwin):** the default fork-based ``Worker`` can trigger **SIGABRT (signal 6)**
in the work-horse with some SSL / Objective-C stacks after fork. This script defaults
to ``SimpleWorker`` (no fork) on Darwin. Override with ``RQ_USE_SIMPLE_WORKER=0`` to
force the standard ``Worker``, or set ``RQ_USE_SIMPLE_WORKER=1`` on Linux to opt in.

Or: ``python -m app.scripts.run_rq_worker``
"""

from __future__ import annotations

import logging
import os
import sys

from redis import Redis
from rq import SimpleWorker, Worker

from app.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _use_simple_worker() -> bool:
    """Prefer no-fork execution on macOS; allow explicit env on any OS."""
    raw = os.environ.get("RQ_USE_SIMPLE_WORKER", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return sys.platform == "darwin"


def main() -> None:
    """Listen on queue ``documents`` until interrupted (SIGINT)."""
    settings = get_settings()
    if not (settings.redis_url or "").strip():
        raise SystemExit("redis_url is empty; set REDIS_URL / redis_url in .env")
    redis_conn = Redis.from_url(settings.redis_url)
    listen = ["documents"]
    use_simple = _use_simple_worker()
    worker_cls = SimpleWorker if use_simple else Worker
    logger.info(
        "Starting RQ %s queues=%s redis=%s",
        worker_cls.__name__,
        listen,
        settings.redis_url,
    )
    worker = worker_cls(listen, connection=redis_conn)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
