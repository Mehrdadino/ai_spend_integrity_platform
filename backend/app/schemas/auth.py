"""HTTP models for platform login and session introspection."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Email/password login (no organization id — tenant chosen after sign-in)."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    """Authenticated user for the UI (platform role + optional home org)."""

    id: uuid.UUID
    organization_id: Optional[uuid.UUID] = None
    email: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    """Bearer token plus user profile."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse
