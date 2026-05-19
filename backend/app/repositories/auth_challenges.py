"""Persist and load short-lived auth challenges (OTP / reset token)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.auth_challenge import AuthChallenge, AuthChallengePurpose


def get_challenge_by_id(
    session: Session,
    *,
    challenge_id: uuid.UUID,
    purpose: str,
) -> Optional[AuthChallenge]:
    """Load an unconsumed challenge for the given purpose."""
    return session.scalar(
        select(AuthChallenge).where(
            AuthChallenge.id == challenge_id,
            AuthChallenge.purpose == purpose,
            AuthChallenge.consumed_at.is_(None),
        )
    )


def get_active_password_reset_for_user(
    session: Session,
    *,
    user_id: uuid.UUID,
) -> Optional[AuthChallenge]:
    """Latest unconsumed password-reset challenge for a user (if any)."""
    now = datetime.now(timezone.utc)
    return session.scalar(
        select(AuthChallenge)
        .where(
            AuthChallenge.user_id == user_id,
            AuthChallenge.purpose == AuthChallengePurpose.PASSWORD_RESET.value,
            AuthChallenge.consumed_at.is_(None),
            AuthChallenge.expires_at > now,
        )
        .order_by(AuthChallenge.created_at.desc())
        .limit(1)
    )


def create_auth_challenge(
    session: Session,
    *,
    user_id: uuid.UUID,
    purpose: str,
    secret_hash: str,
    expires_at: datetime,
) -> AuthChallenge:
    """Insert a challenge; caller should invalidate prior rows for same user/purpose first."""
    row = AuthChallenge(
        user_id=user_id,
        purpose=purpose,
        secret_hash=secret_hash,
        expires_at=expires_at,
    )
    session.add(row)
    session.flush()
    return row


def invalidate_challenges_for_user(
    session: Session,
    *,
    user_id: uuid.UUID,
    purpose: str,
) -> None:
    """Remove pending challenges so only the newest email flow is valid."""
    session.execute(
        delete(AuthChallenge).where(
            AuthChallenge.user_id == user_id,
            AuthChallenge.purpose == purpose,
            AuthChallenge.consumed_at.is_(None),
        )
    )


def mark_challenge_consumed(session: Session, challenge: AuthChallenge) -> None:
    """Mark a challenge used (OTP verified or password reset completed)."""
    challenge.consumed_at = datetime.now(timezone.utc)
    session.flush()
