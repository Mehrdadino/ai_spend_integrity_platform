"""Org team: members, invites (B2B membership)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_org_admin_for_path_org, require_org_member_for_path_org
from app.api.rate_limit_deps import rate_limit_auth_ip
from app.services.rate_limit import enforce_rate_limit_email
from app.db.session import get_db
from app.models.organization import Organization
from app.models.organization_member import OrgMemberRole
from app.models.user import User
from app.repositories.organization_invites import list_pending_invites_for_organization
from app.repositories.organization_members import (
    count_active_org_admins,
    deactivate_organization_member,
    get_membership,
    is_active_member,
    list_members_for_organization,
    update_member_role,
)
from app.schemas.organization_team import (
    CreateOrganizationInviteRequest,
    OrganizationInviteResponse,
    OrganizationMemberResponse,
    OrganizationTeamRosterRowResponse,
    UpdateOrganizationMemberRequest,
)
from app.services.organization_invites import InviteError, create_invite
from app.services.organization_team import build_team_roster

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _member_response(member) -> OrganizationMemberResponse:
    deactivated_by = getattr(member, "deactivated_by", None)
    return OrganizationMemberResponse(
        user_id=member.user_id,
        email=member.user.email,
        role=member.role,
        created_at=member.created_at,
        deactivated_at=member.deactivated_at,
        deactivated_by_email=deactivated_by.email if deactivated_by is not None else None,
    )


@router.get(
    "/{organization_id}/team",
    response_model=list[OrganizationTeamRosterRowResponse],
)
def get_organization_team(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db),
    _ctx: tuple[Organization, User] = Depends(require_org_member_for_path_org),
) -> list[OrganizationTeamRosterRowResponse]:
    """Team directory: all members and open invites with status (any org member)."""
    rows = build_team_roster(db, organization_id=organization_id)
    return [OrganizationTeamRosterRowResponse.model_validate(r) for r in rows]


@router.get("/{organization_id}/members", response_model=list[OrganizationMemberResponse])
def get_organization_members(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db),
    _ctx: tuple[Organization, User] = Depends(require_org_member_for_path_org),
) -> list[OrganizationMemberResponse]:
    """List team members (any org member; use ``/team`` for invite status)."""
    rows = list_members_for_organization(db, organization_id=organization_id)
    return [_member_response(m) for m in rows]


@router.get("/{organization_id}/invites", response_model=list[OrganizationInviteResponse])
def get_organization_invites(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db),
    _ctx: tuple[Organization, User] = Depends(require_org_admin_for_path_org),
) -> list[OrganizationInviteResponse]:
    """Pending invites for this org (org admin; roster includes open invites for all members)."""
    rows = list_pending_invites_for_organization(db, organization_id=organization_id)
    return [OrganizationInviteResponse.model_validate(r) for r in rows]


@router.post(
    "/{organization_id}/invites",
    response_model=OrganizationInviteResponse,
    status_code=201,
    dependencies=[Depends(rate_limit_auth_ip("org_invite"))],
)
def post_organization_invite(
    organization_id: uuid.UUID,
    body: CreateOrganizationInviteRequest,
    db: Session = Depends(get_db),
    ctx: tuple[Organization, User] = Depends(require_org_admin_for_path_org),
) -> OrganizationInviteResponse:
    """Invite a user by email (org admin)."""
    org, user = ctx
    enforce_rate_limit_email("org_invite", str(body.email))
    try:
        created = create_invite(
            db,
            organization_id=org.id,
            email=str(body.email),
            role=body.role,
            invited_by=user,
        )
        db.commit()
    except InviteError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    from app.models.organization_invite import OrganizationInvite

    row = db.get(OrganizationInvite, created.invite_id)
    if row is None:
        raise HTTPException(status_code=500, detail="Invite created but not found")
    return OrganizationInviteResponse.model_validate(row)


@router.patch(
    "/{organization_id}/members/{user_id}",
    response_model=OrganizationMemberResponse,
)
def patch_organization_member(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    body: UpdateOrganizationMemberRequest,
    db: Session = Depends(get_db),
    ctx: tuple[Organization, User] = Depends(require_org_admin_for_path_org),
) -> OrganizationMemberResponse:
    """Change a member's org role."""
    org, actor = ctx
    member = get_membership(db, organization_id=org.id, user_id=user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if not is_active_member(member):
        raise HTTPException(status_code=400, detail="Cannot change role for a deactivated member")
    try:
        new_role = body.role.strip().lower()
        if new_role not in {r.value for r in OrgMemberRole}:
            raise ValueError("Invalid role")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if member.role == OrgMemberRole.ORG_ADMIN.value and new_role != OrgMemberRole.ORG_ADMIN.value:
        if count_active_org_admins(db, organization_id=org.id) <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last org admin")

    update_member_role(db, member, role=new_role)
    db.commit()
    db.refresh(member)
    return _member_response(member)


@router.post(
    "/{organization_id}/members/{user_id}/deactivate",
    response_model=OrganizationMemberResponse,
)
def post_deactivate_organization_member(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    ctx: tuple[Organization, User] = Depends(require_org_admin_for_path_org),
) -> OrganizationMemberResponse:
    """Soft-deactivate a member (including other org admins when another admin remains)."""
    org, actor = ctx
    member = get_membership(db, organization_id=org.id, user_id=user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if not is_active_member(member):
        raise HTTPException(status_code=400, detail="Member is already deactivated")
    if member.role == OrgMemberRole.ORG_ADMIN.value and count_active_org_admins(db, organization_id=org.id) <= 1:
        raise HTTPException(status_code=400, detail="Cannot deactivate the last org admin")

    deactivate_organization_member(db, member, deactivated_by_user_id=actor.id)
    db.commit()
    db.refresh(member)
    return OrganizationMemberResponse(
        user_id=member.user_id,
        email=member.user.email,
        role=member.role,
        created_at=member.created_at,
        deactivated_at=member.deactivated_at,
        deactivated_by_email=actor.email,
    )
