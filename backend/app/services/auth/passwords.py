"""Bcrypt password hashing for org user login (P1)."""

from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    """Return a bcrypt hash string suitable for ``users.password_hash``."""
    raw = plain.encode("utf-8")
    digest = bcrypt.hashpw(raw, bcrypt.gensalt())
    return digest.decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    """Constant-time compare of ``plain`` against stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
