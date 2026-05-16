"""Organization API: list/create scoped by platform role and org ownership."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.organizations import (
    OrganizationSlugConflictError,
    create_organization,
    list_organizations_for_user,
)
from app.schemas.organizations import CreateOrganizationRequest, OrganizationResponse

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=list[OrganizationResponse])
def get_organizations(
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
    limit: int = Query(200, ge=1, le=500, description="Max organizations returned (newest first)"),
) -> list[OrganizationResponse]:
    """Platform admins: all orgs. Members: only orgs they created."""
    rows = list_organizations_for_user(db, user=user, limit=limit)
    return [OrganizationResponse.model_validate(r) for r in rows]


@router.post("", response_model=OrganizationResponse, status_code=201)
def post_organization(
    body: CreateOrganizationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
) -> OrganizationResponse:
    """Create a tenant; the signed-in user becomes ``created_by_user_id``."""
    try:
        org = create_organization(
            db,
            name=body.name,
            slug=body.slug,
            created_by_user_id=user.id,
        )
        db.commit()
    except OrganizationSlugConflictError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OrganizationResponse.model_validate(org)
