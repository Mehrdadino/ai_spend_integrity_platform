"""CLI: run one RQ worker process for the ``documents`` queue (step 1d).

Start Redis (e.g. ``docker compose up -d redis``), then from ``backend/``::

  document-worker

RQ **2.x** removed ``rq.Connection``; pass ``connection=`` into ``Worker`` instead.

Or: ``python -m app.scripts.run_rq_worker``
"""

from __future__ import annotations

import logging

from redis import Redis
from rq import Worker

from app.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """Listen on queue ``documents`` until interrupted (SIGINT)."""
    settings = get_settings()
    if not (settings.redis_url or "").strip():
        raise SystemExit("redis_url is empty; set REDIS_URL / redis_url in .env")
    redis_conn = Redis.from_url(settings.redis_url)
    listen = ["documents"]
    logger.info("Starting RQ worker queues=%s redis=%s", listen, settings.redis_url)
    worker = Worker(listen, connection=redis_conn)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
