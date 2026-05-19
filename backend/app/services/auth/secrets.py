"""One-time codes and reset tokens for email auth flows."""

from __future__ import annotations

import secrets
import string


def generate_login_otp(*, length: int = 6) -> str:
    """Return a numeric OTP suitable for email 2FA."""
    digits = string.digits
    return "".join(secrets.choice(digits) for _ in range(length))


def generate_password_reset_token() -> str:
    """URL-safe opaque token embedded in the reset link (not stored in plain text)."""
    return secrets.token_urlsafe(32)
