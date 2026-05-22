"""HTTP models for org membership and invites."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.auth import UserResponse
from app.services.auth.password_policy import password_validation_errors


class OrganizationMemberResponse(BaseModel):
    """Member row for team management UI."""

    user_id: uuid.UUID
    email: str
    role: str
    created_at: datetime
    deactivated_at: Optional[datetime] = None
    deactivated_by_email: Optional[str] = None

    model_config = {"from_attributes": True}


class OrganizationInviteResponse(BaseModel):
    """Pending invite (no token exposed)."""

    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class OrganizationTeamRosterRowResponse(BaseModel):
    """One directory row: active member or outstanding invite with status."""

    row_type: Literal["member", "invite"]
    email: str
    role: str
    status: str
    status_label: str
    user_id: Optional[uuid.UUID] = None
    invite_id: Optional[uuid.UUID] = None
    joined_at: Optional[datetime] = None
    invited_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    deactivated_at: Optional[datetime] = None
    deactivated_by_email: Optional[str] = None

    model_config = {"from_attributes": True}


class CreateOrganizationInviteRequest(BaseModel):
    """Org admin invites a colleague by email."""

    email: EmailStr
    role: str = Field(default="member", description="org_admin | member | viewer")


class UpdateOrganizationMemberRequest(BaseModel):
    """Change a member's org role."""

    role: str


class OrganizationInvitePreviewResponse(BaseModel):
    """Public invite metadata for the set-password / sign-in UI (no secrets)."""

    email: str
    organization_id: uuid.UUID
    organization_name: str
    role: str
    account_exists: bool


class ActivateOrganizationInviteRequest(BaseModel):
    """New invitee: create account and join org (token proves email ownership)."""

    invite_token: str = Field(min_length=16, max_length=256)
    password: str = Field(max_length=128)
    remember_device: bool = False

    @field_validator("password")
    @classmethod
    def password_meets_policy(cls, value: str) -> str:
        errors = password_validation_errors(value)
        if errors:
            raise ValueError(" ".join(errors))
        return value


class ActivateOrganizationInviteResponse(BaseModel):
    """JWT plus org context after invite activation."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    organization_id: uuid.UUID
    organization_name: str
    role: str
    message: str


class AcceptOrganizationInviteRequest(BaseModel):
    """Redeem invite token after sign-in (existing accounts)."""

    invite_token: str = Field(min_length=16, max_length=256)


class AcceptOrganizationInviteResponse(BaseModel):
    """Organization the user just joined."""

    organization_id: uuid.UUID
    organization_name: str
    role: str
    message: str
