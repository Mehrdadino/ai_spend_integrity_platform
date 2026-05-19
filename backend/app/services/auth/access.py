"""Platform vs per-org membership access checks."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.organization_member import OrgMemberRole
from app.models.user import PlatformRole, User
from app.repositories.organization_members import get_membership


def is_platform_admin(user: User) -> bool:
    """True when the user may list and open every organization."""
    return user.role == PlatformRole.ADMIN.value


def get_org_role_for_user(
    session: Session,
    *,
    user: User,
    organization_id: uuid.UUID,
) -> Optional[str]:
    """Return per-org role string, or None if not a member (platform admins return org_admin)."""
    if is_platform_admin(user):
        return OrgMemberRole.ORG_ADMIN.value
    membership = get_membership(session, organization_id=organization_id, user_id=user.id)
    return membership.role if membership else None


def user_can_access_organization(session: Session, user: User, org: Organization) -> bool:
    """Any org member (or platform admin) may open the tenant."""
    return get_org_role_for_user(session, user=user, organization_id=org.id) is not None


def user_can_manage_organization(session: Session, user: User, org: Organization) -> bool:
    """Org admin: invites, sites, delete docs, batch materialize."""
    role = get_org_role_for_user(session, user=user, organization_id=org.id)
    return role == OrgMemberRole.ORG_ADMIN.value


def user_can_write_organization(session: Session, user: User, org: Organization) -> bool:
    """Upload bills and apply review actions (member or org admin)."""
    role = get_org_role_for_user(session, user=user, organization_id=org.id)
    return role in (OrgMemberRole.ORG_ADMIN.value, OrgMemberRole.MEMBER.value)
