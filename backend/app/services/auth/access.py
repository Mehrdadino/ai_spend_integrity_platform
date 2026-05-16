"""Platform vs org access checks (who may see or manage a tenant)."""

from __future__ import annotations

import uuid

from app.models.organization import Organization
from app.models.user import PlatformRole, User


def is_platform_admin(user: User) -> bool:
    """True when the user may list and open every organization."""
    return user.role == PlatformRole.ADMIN.value


def user_can_access_organization(user: User, org: Organization) -> bool:
    """Members may only access organizations they created; platform admins see all."""
    if is_platform_admin(user):
        return True
    return org.created_by_user_id is not None and org.created_by_user_id == user.id


def user_can_manage_organization(user: User, org: Organization) -> bool:
    """Site create, document delete, batch materialize — org owner or platform admin."""
    return user_can_access_organization(user, org)
