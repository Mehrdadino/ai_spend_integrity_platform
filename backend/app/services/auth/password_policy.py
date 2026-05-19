"""Password strength rules for new passwords (register, reset, change).

Uses an allowlist of ASCII letters, digits, and common safe symbols (no spaces or quotes).
Current-password checks on login are not validated here — users may still have older passwords.
"""

from __future__ import annotations

import re
from typing import List

# Printable specials allowed in new passwords (excludes space, quotes, backslash, backtick).
ALLOWED_SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?/"
_ALLOWED_CHAR_PATTERN = re.compile(
    rf"^[A-Za-z0-9{re.escape(ALLOWED_SPECIAL_CHARS)}]+$"
)

_MIN_LENGTH = 8
_MAX_LENGTH = 128


def password_validation_errors(password: str) -> List[str]:
    """Return human-readable issues; empty list means the password is acceptable."""
    issues: List[str] = []

    if len(password) < _MIN_LENGTH:
        issues.append(f"Use at least {_MIN_LENGTH} characters.")
    if len(password) > _MAX_LENGTH:
        issues.append(f"Use at most {_MAX_LENGTH} characters.")

    if password and not _ALLOWED_CHAR_PATTERN.match(password):
        issues.append(
            "Use only letters, numbers, and these symbols: "
            + " ".join(ALLOWED_SPECIAL_CHARS)
        )

    if password and not re.search(r"[a-z]", password):
        issues.append("Include at least one lowercase letter.")
    if password and not re.search(r"[A-Z]", password):
        issues.append("Include at least one uppercase letter.")
    if password and not re.search(r"\d", password):
        issues.append("Include at least one number.")
    if password and not any(ch in ALLOWED_SPECIAL_CHARS for ch in password):
        issues.append(
            "Include at least one special character (for example ! @ # $ %)."
        )

    return issues


def assert_password_acceptable(password: str) -> None:
    """Raise ``ValueError`` with joined messages when the password fails policy."""
    errors = password_validation_errors(password)
    if errors:
        raise ValueError(" ".join(errors))
