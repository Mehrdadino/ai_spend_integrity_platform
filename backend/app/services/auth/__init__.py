"""P1 JWT auth: password hashing, email challenges, and access-token helpers."""

from app.services.auth.challenges import (
    ChallengeError,
    complete_password_reset,
    start_login_otp_challenge,
    start_password_reset_challenge,
    verify_login_otp_challenge,
)
from app.services.auth.jwt_tokens import create_access_token, decode_access_token
from app.services.auth.passwords import hash_password, verify_password

__all__ = [
    "ChallengeError",
    "complete_password_reset",
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "start_login_otp_challenge",
    "start_password_reset_challenge",
    "verify_login_otp_challenge",
    "verify_password",
]
