"""HTTP models for org membership and invites."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class OrganizationMemberResponse(BaseModel):
    """Member row for team management UI."""

    user_id: uuid.UUID
    email: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class OrganizationInviteResponse(BaseModel):
    """Pending invite (no token exposed)."""

    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateOrganizationInviteRequest(BaseModel):
    """Org admin invites a colleague by email."""

    email: EmailStr
    role: str = Field(default="member", description="org_admin | member | viewer")


class UpdateOrganizationMemberRequest(BaseModel):
    """Change a member's org role."""

    role: str


class AcceptOrganizationInviteRequest(BaseModel):
    """Redeem invite token after sign-in."""

    invite_token: str = Field(min_length=16, max_length=256)


class AcceptOrganizationInviteResponse(BaseModel):
    """Organization the user just joined."""

    organization_id: uuid.UUID
    organization_name: str
    role: str
    message: str
