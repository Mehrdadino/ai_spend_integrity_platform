"""Org-scoped sites API for upload and document viewer pickers (UI-first)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_admin, require_auth_context
from app.db.session import get_db
from app.repositories.sites import ensure_site, list_sites_for_organization
from app.schemas.sites import CreateSiteRequest, SiteResponse

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("", response_model=list[SiteResponse])
def get_sites(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
    limit: int = Query(200, ge=1, le=500),
) -> list[SiteResponse]:
    """List sites for the authenticated organization (alphabetical by name)."""
    rows = list_sites_for_organization(db, organization_id=ctx.organization.id, limit=limit)
    return [SiteResponse.model_validate(r) for r in rows]


@router.post("", response_model=SiteResponse, status_code=201)
def post_site(
    body: CreateSiteRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> SiteResponse:
    """Create a site by name (org admin). Idempotent when the name already exists."""
    site = ensure_site(db, organization_id=ctx.organization.id, name=body.name.strip())
    return SiteResponse.model_validate(site)
