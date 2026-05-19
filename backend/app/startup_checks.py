"""Fail fast when production is misconfigured (weak secrets, dev bypasses)."""

from __future__ import annotations

import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

_INSECURE_JWT_SECRETS = frozenset(
    {
        "change-me-in-production",
        "changeme",
        "secret",
        "dev",
    }
)


def validate_settings_for_runtime() -> None:
    """Log warnings in dev; raise on dangerous production configuration."""
    settings = get_settings()
    if settings.app_env != "production":
        if settings.jwt_secret_key in _INSECURE_JWT_SECRETS or len(settings.jwt_secret_key) < 32:
            logger.warning(
                "JWT_SECRET_KEY is weak — set a 32+ character secret before deploying to production."
            )
        if settings.auth_allow_dev_org_header:
            logger.warning("AUTH_ALLOW_DEV_ORG_HEADER is enabled — disable in production.")
        return

    errors: list[str] = []
    if not (settings.redis_url or "").strip():
        errors.append("REDIS_URL must be set in production (rate limits, lockout, workers).")
    if settings.jwt_secret_key in _INSECURE_JWT_SECRETS or len(settings.jwt_secret_key) < 32:
        errors.append("JWT_SECRET_KEY must be a unique string of at least 32 characters.")
    if settings.auth_allow_dev_org_header:
        errors.append("AUTH_ALLOW_DEV_ORG_HEADER must be false in production.")
    if settings.auth_allow_registration:
        logger.warning(
            "AUTH_ALLOW_REGISTRATION is true in production — prefer invite-only unless intentional."
        )
    if not settings.rate_limit_enabled:
        errors.append("RATE_LIMIT_ENABLED must be true in production.")

    if errors:
        raise RuntimeError("Unsafe production configuration:\n- " + "\n- ".join(errors))
