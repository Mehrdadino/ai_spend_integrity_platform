"""Temporary account lockout after repeated failed password attempts (Redis)."""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

from fastapi import HTTPException
from redis import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:32]


def _redis() -> Optional[Redis]:
    from app.services.rate_limit import _get_redis

    return _get_redis()


def assert_login_not_locked(email: str) -> None:
    """Raise 429 if this email is in a lockout window."""
    settings = get_settings()
    if settings.auth_lockout_max_failures <= 0:
        return
    redis = _redis()
    if redis is None:
        return
    key = f"lockout:block:{_email_hash(email)}"
    try:
        if redis.exists(key):
            ttl = redis.ttl(key)
            retry = max(int(ttl), 1) if ttl and ttl > 0 else settings.auth_lockout_minutes * 60
            raise HTTPException(
                status_code=429,
                detail="Too many failed sign-in attempts. Try again later or reset your password.",
                headers={"Retry-After": str(retry)},
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("auth_lockout: Redis check failed (allowing login): %s", exc)


def record_login_failure(email: str) -> None:
    """Increment failure counter; set block key when threshold exceeded."""
    settings = get_settings()
    if settings.auth_lockout_max_failures <= 0:
        return
    redis = _redis()
    if redis is None:
        return
    eh = _email_hash(email)
    fail_key = f"lockout:fail:{eh}"
    block_key = f"lockout:block:{eh}"
    window = settings.auth_lockout_minutes * 60
    try:
        count = int(redis.incr(fail_key))
        if count == 1:
            redis.expire(fail_key, window)
        if count >= settings.auth_lockout_max_failures:
            redis.setex(block_key, window, "1")
            redis.delete(fail_key)
    except Exception as exc:
        logger.warning("auth_lockout: Redis record failure failed: %s", exc)


def clear_login_failures(email: str) -> None:
    """Clear counters after successful password verification."""
    redis = _redis()
    if redis is None:
        return
    eh = _email_hash(email)
    try:
        redis.delete(f"lockout:fail:{eh}", f"lockout:block:{eh}")
    except Exception as exc:
        logger.warning("auth_lockout: Redis clear failed: %s", exc)
