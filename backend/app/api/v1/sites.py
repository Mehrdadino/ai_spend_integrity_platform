"""Org-scoped sites API for upload and document viewer pickers (UI-first)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_organization
from app.db.session import get_db
from app.models.organization import Organization
from app.repositories.sites import ensure_site, list_sites_for_organization
from app.schemas.sites import CreateSiteRequest, SiteResponse

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("", response_model=list[SiteResponse])
def get_sites(
    db: Session = Depends(get_db),
    org: Organization = Depends(require_organization),
    limit: int = Query(200, ge=1, le=500),
) -> list[SiteResponse]:
    """List sites for ``X-Organization-Id`` (alphabetical by name)."""
    rows = list_sites_for_organization(db, organization_id=org.id, limit=limit)
    return [SiteResponse.model_validate(r) for r in rows]


@router.post("", response_model=SiteResponse, status_code=201)
def post_site(
    body: CreateSiteRequest,
    db: Session = Depends(get_db),
    org: Organization = Depends(require_organization),
) -> SiteResponse:
    """Create a site by name, or return the existing row with the same name (idempotent)."""
    site = ensure_site(db, organization_id=org.id, name=body.name.strip())
    return SiteResponse.model_validate(site)
