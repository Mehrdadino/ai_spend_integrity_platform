"""Request/response models for organization list + create (dev admin API)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateOrganizationRequest(BaseModel):
    """Body for ``POST /organizations``; ``slug`` is stored lowercase (URL-safe tenant key)."""

    name: str = Field(..., min_length=1, max_length=255, examples=["Acme Corp"])
    slug: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*$",
        description="Lowercase letters, digits, hyphens; normalized to lowercase on save.",
        examples=["acme-corp"],
    )


class OrganizationResponse(BaseModel):
    """One tenant row returned from list or create (Postgres metadata only)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_at: datetime
    my_role: Optional[str] = Field(
        default=None,
        description="Signed-in user's role in this org (org_admin | member | viewer).",
    )
