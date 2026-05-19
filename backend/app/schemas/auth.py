"""HTTP models for platform auth: register, login + email 2FA, password reset."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.services.auth.password_policy import password_validation_errors


def _validate_new_password(value: str) -> str:
    """Shared strength check for passwords being created or replaced."""
    errors = password_validation_errors(value)
    if errors:
        raise ValueError(" ".join(errors))
    return value


class RegisterRequest(BaseModel):
    """Create a platform account (email is the login identifier)."""

    email: EmailStr
    password: str = Field(max_length=128)

    @field_validator("password")
    @classmethod
    def password_meets_policy(cls, value: str) -> str:
        return _validate_new_password(value)


class LoginRequest(BaseModel):
    """First step: email/password; triggers an email OTP (no JWT until verified)."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    remember_device: bool = False


class VerifyLoginOtpRequest(BaseModel):
    """Second step: OTP from email plus the challenge id from ``POST /auth/login``."""

    challenge_id: uuid.UUID
    code: str = Field(min_length=4, max_length=16)
    remember_device: bool = False


class ChangePasswordRequest(BaseModel):
    """Signed-in user replaces password (requires current password)."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(max_length=128)

    @field_validator("new_password")
    @classmethod
    def new_password_meets_policy(cls, value: str) -> str:
        return _validate_new_password(value)


class ChangeEmailRequest(BaseModel):
    """Signed-in user replaces login email (requires current password)."""

    new_email: EmailStr
    current_password: str = Field(min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    """Request a reset link (email is only sent when the account exists)."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Set a new password using the token from the reset email link."""

    reset_token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(max_length=128)

    @field_validator("new_password")
    @classmethod
    def new_password_meets_policy(cls, value: str) -> str:
        return _validate_new_password(value)


class UserResponse(BaseModel):
    """Authenticated user for the UI (platform role + optional home org)."""

    id: uuid.UUID
    organization_id: Optional[uuid.UUID] = None
    email: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    """Bearer token plus user profile (after email OTP verification)."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class LoginChallengeResponse(BaseModel):
    """After password check: JWT when email 2FA is off (no SMTP), else OTP challenge."""

    message: str
    challenge_id: Optional[uuid.UUID] = None
    access_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[UserResponse] = None


class MessageResponse(BaseModel):
    """Generic success copy (forgot-password, register)."""

    message: str


class RegisterResponse(BaseModel):
    """Account created; user signs in via login + email OTP."""

    message: str
    user: UserResponse
