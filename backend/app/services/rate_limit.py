"""Redis-backed fixed-window rate limits (auth abuse protection in production)."""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

from fastapi import HTTPException, Request
from redis import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)


class RateLimitExceeded(HTTPException):
    """HTTP 429 when a client exceeds a configured limit."""

    def __init__(self, *, retry_after_seconds: int) -> None:
        super().__init__(
            status_code=429,
            detail="Too many requests. Please wait and try again.",
            headers={"Retry-After": str(retry_after_seconds)},
        )


_redis_client: Optional[Redis] = None


def _get_redis() -> Optional[Redis]:
    """Lazy Redis connection for rate limiting (same URL as RQ)."""
    global _redis_client
    settings = get_settings()
    url = (settings.redis_url or "").strip()
    if not url:
        return None
    if _redis_client is None:
        _redis_client = Redis.from_url(url, decode_responses=True)
    return _redis_client


def client_ip(request: Request) -> str:
    """Client IP; honors ``X-Forwarded-For`` when ``trust_forwarded_for`` is enabled."""
    settings = get_settings()
    if settings.trust_forwarded_for:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _email_key(email: str) -> str:
    """Hash email for Redis keys (avoid storing raw addresses in key names)."""
    digest = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:32]
    return digest


def check_rate_limit(*, key: str, limit: int, window_seconds: int) -> None:
    """Increment a counter; raise ``RateLimitExceeded`` when over ``limit`` in the window."""
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return

    redis = _get_redis()
    if redis is None:
        if settings.app_env == "production":
            logger.error("rate_limit: Redis unavailable in production — rejecting request")
            raise HTTPException(
                status_code=503,
                detail="Rate limiting unavailable; try again later.",
            )
        logger.warning("rate_limit: Redis not configured — skipping limit for key=%s", key)
        return

    redis_key = f"rl:{key}:{window_seconds}"
    try:
        count = int(redis.incr(redis_key))
        if count == 1:
            redis.expire(redis_key, window_seconds)
        if count > limit:
            ttl = redis.ttl(redis_key)
            retry = max(int(ttl), 1) if ttl and ttl > 0 else window_seconds
            raise RateLimitExceeded(retry_after_seconds=retry)
    except RateLimitExceeded:
        raise
    except Exception as exc:
        if settings.app_env == "production":
            logger.exception("rate_limit: Redis error")
            raise HTTPException(status_code=503, detail="Rate limiting unavailable.") from exc
        logger.warning("rate_limit: Redis error (dev) — allowing request: %s", exc)


def _email_limit_for_action(action: str) -> int:
    """Action-specific caps (sensitive email flows use the stricter bucket)."""
    settings = get_settings()
    if action in ("forgot_password", "register", "org_invite"):
        return settings.auth_rate_limit_sensitive_email_per_15min
    if action == "verify_2fa":
        return settings.auth_rate_limit_verify_2fa_per_15min
    return settings.auth_rate_limit_login_email_per_15min


def enforce_rate_limit_ip(request: Request, action: str) -> None:
    """Per-IP limit for an auth action (e.g. login, forgot-password)."""
    settings = get_settings()
    ip = client_ip(request)
    check_rate_limit(
        key=f"ip:{action}:{ip}",
        limit=settings.auth_rate_limit_ip_per_minute,
        window_seconds=60,
    )


def enforce_rate_limit_email(action: str, identifier: str) -> None:
    """Per-email (or per-challenge) limit — slows stuffing and email abuse."""
    check_rate_limit(
        key=f"email:{action}:{_email_key(identifier)}",
        limit=_email_limit_for_action(action),
        window_seconds=15 * 60,
    )
