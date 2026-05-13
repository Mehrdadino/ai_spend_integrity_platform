"""Organization admin HTTP API: list all tenants and create new ones (dev UI).

These routes intentionally **do not** require ``X-Organization-Id`` so operators can
bootstrap tenants before any org-scoped upload. **Add authentication** (or disable
create in production) before exposing this API on the public internet.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.organizations import (
    OrganizationSlugConflictError,
    create_organization,
    list_organizations,
)
from app.schemas.organizations import CreateOrganizationRequest, OrganizationResponse

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationResponse])
def get_organizations(
    db: Session = Depends(get_db),
    limit: int = Query(200, ge=1, le=500, description="Max organizations returned (newest first)"),
) -> list[OrganizationResponse]:
    """Return every organization id, name, slug, and ``created_at`` for the dev picker UI."""
    rows = list_organizations(db, limit=limit)
    return [OrganizationResponse.model_validate(r) for r in rows]


@router.post("", response_model=OrganizationResponse, status_code=201)
def post_organization(
    body: CreateOrganizationRequest,
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    """Create a tenant; **409** if ``slug`` is already taken; **400** if slug fails normalization rules."""
    try:
        org = create_organization(db, name=body.name, slug=body.slug)
    except OrganizationSlugConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OrganizationResponse.model_validate(org)
