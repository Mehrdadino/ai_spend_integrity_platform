"""HTTP models for org-scoped ``sites`` (locations under a tenant)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SiteResponse(BaseModel):
    """One site row for picker UIs."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    created_at: datetime


class CreateSiteRequest(BaseModel):
    """Create a facility / store name unique per org by display name (idempotent in repo)."""

    name: str = Field(..., min_length=1, max_length=255)
