"""Create and verify login OTP and password-reset challenges (hashed secrets in Postgres)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.auth_challenge import AuthChallenge, AuthChallengePurpose
from app.models.user import User
from app.repositories.auth_challenges import (
    create_auth_challenge,
    get_challenge_by_id,
    invalidate_challenges_for_user,
    mark_challenge_consumed,
)
from app.services.auth.email_delivery import send_login_otp_email, send_password_reset_email
from app.services.auth.passwords import hash_password, verify_password
from app.services.auth.secrets import generate_login_otp, generate_password_reset_token


class ChallengeError(ValueError):
    """Invalid, expired, or already-used challenge."""


@dataclass(frozen=True)
class LoginOtpChallengeResult:
    """Opaque id returned to the client between password check and OTP verify."""

    challenge_id: uuid.UUID


@dataclass(frozen=True)
class PasswordResetChallengeResult:
    """Plain reset token for the email link (stored hashed in DB)."""

    reset_token: str


def _expires_at(*, minutes: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _is_expired(challenge: AuthChallenge) -> bool:
    return challenge.expires_at <= datetime.now(timezone.utc)


def start_login_otp_challenge(session: Session, *, user: User) -> LoginOtpChallengeResult:
    """Invalidate prior OTPs, persist a new code, and email it to the user."""
    settings = get_settings()
    otp = generate_login_otp()
    invalidate_challenges_for_user(
        session,
        user_id=user.id,
        purpose=AuthChallengePurpose.LOGIN_OTP.value,
    )
    challenge = create_auth_challenge(
        session,
        user_id=user.id,
        purpose=AuthChallengePurpose.LOGIN_OTP.value,
        secret_hash=hash_password(otp),
        expires_at=_expires_at(minutes=settings.auth_otp_expire_minutes),
    )
    send_login_otp_email(
        to_email=user.email,
        otp_code=otp,
        expire_minutes=settings.auth_otp_expire_minutes,
    )
    return LoginOtpChallengeResult(challenge_id=challenge.id)


def verify_login_otp_challenge(
    session: Session,
    *,
    challenge_id: uuid.UUID,
    otp_code: str,
) -> User:
    """Validate OTP and return the user to mint a JWT."""
    challenge = get_challenge_by_id(
        session,
        challenge_id=challenge_id,
        purpose=AuthChallengePurpose.LOGIN_OTP.value,
    )
    if challenge is None:
        raise ChallengeError("Invalid or expired verification code")
    if _is_expired(challenge):
        raise ChallengeError("Verification code has expired")
    if not verify_password(otp_code.strip(), challenge.secret_hash):
        raise ChallengeError("Invalid or expired verification code")

    user = challenge.user
    mark_challenge_consumed(session, challenge)
    return user


def start_password_reset_challenge(session: Session, *, user: User) -> PasswordResetChallengeResult:
    """Create a reset token, email the link, and invalidate prior reset rows for this user."""
    settings = get_settings()
    token = generate_password_reset_token()
    invalidate_challenges_for_user(
        session,
        user_id=user.id,
        purpose=AuthChallengePurpose.PASSWORD_RESET.value,
    )
    create_auth_challenge(
        session,
        user_id=user.id,
        purpose=AuthChallengePurpose.PASSWORD_RESET.value,
        secret_hash=hash_password(token),
        expires_at=_expires_at(minutes=settings.auth_reset_expire_minutes),
    )
    reset_url = f"{settings.auth_frontend_base_url.rstrip('/')}/?reset_token={token}"
    send_password_reset_email(
        to_email=user.email,
        reset_url=reset_url,
        expire_minutes=settings.auth_reset_expire_minutes,
    )
    return PasswordResetChallengeResult(reset_token=token)


def verify_password_reset_token(
    session: Session,
    *,
    reset_token: str,
) -> Optional[AuthChallenge]:
    """Find an active password-reset challenge matching the token (does not consume)."""
    now = datetime.now(timezone.utc)
    # Scan active reset rows (low volume at MVP scale).
    rows = session.scalars(
        select(AuthChallenge).where(
            AuthChallenge.purpose == AuthChallengePurpose.PASSWORD_RESET.value,
            AuthChallenge.consumed_at.is_(None),
            AuthChallenge.expires_at > now,
        )
    ).all()
    token = reset_token.strip()
    for row in rows:
        if verify_password(token, row.secret_hash):
            return row
    return None


def complete_password_reset(
    session: Session,
    *,
    reset_token: str,
    new_password: str,
) -> User:
    """Set a new password and consume the reset challenge."""
    challenge = verify_password_reset_token(session, reset_token=reset_token)
    if challenge is None:
        raise ChallengeError("Invalid or expired reset link")
    user = challenge.user
    user.password_hash = hash_password(new_password)
    mark_challenge_consumed(session, challenge)
    return user
