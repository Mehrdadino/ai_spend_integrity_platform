"""JWT access tokens: ``user_id`` + platform ``role`` + ``email`` (no tenant in token)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.config import get_settings


class TokenValidationError(ValueError):
    """Raised when a bearer token is missing required claims or is expired."""


@dataclass(frozen=True)
class AccessTokenClaims:
    """Decoded bearer token for request dependencies."""

    user_id: uuid.UUID
    role: str
    email: str


def create_access_token(
    *,
    user_id: uuid.UUID,
    role: str,
    email: str,
) -> str:
    """Mint a signed JWT for ``Authorization: Bearer`` clients."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> AccessTokenClaims:
    """Validate signature and expiry; map claims to ``AccessTokenClaims``."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise TokenValidationError("Invalid or expired token") from exc

    sub = payload.get("sub")
    role = payload.get("role")
    email = payload.get("email")
    if not sub or not role or not email:
        raise TokenValidationError("Token missing required claims")
    try:
        user_id = uuid.UUID(str(sub))
    except ValueError as exc:
        raise TokenValidationError("Token has invalid user id") from exc
    return AccessTokenClaims(
        user_id=user_id,
        role=str(role),
        email=str(email),
    )
