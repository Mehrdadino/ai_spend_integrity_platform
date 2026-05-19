"""Organization API: list/create scoped by membership; team routes in ``organization_team``."""

from __future__ import annotations

import uuid

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
from app.services.auth.access import get_org_role_for_user

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _org_response(session: Session, org, user: User) -> OrganizationResponse:
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        created_at=org.created_at,
        my_role=get_org_role_for_user(session, user=user, organization_id=org.id),
    )


@router.get("", response_model=list[OrganizationResponse])
def get_organizations(
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
    limit: int = Query(200, ge=1, le=500, description="Max organizations returned (newest first)"),
) -> list[OrganizationResponse]:
    """Platform admins: all orgs. Others: orgs they are a member of."""
    rows = list_organizations_for_user(db, user=user, limit=limit)
    return [_org_response(db, r, user) for r in rows]


@router.post("", response_model=OrganizationResponse, status_code=201)
def post_organization(
    body: CreateOrganizationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
) -> OrganizationResponse:
    """Create a tenant; the signed-in user becomes ``org_admin`` member."""
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
    return _org_response(db, org, user)
