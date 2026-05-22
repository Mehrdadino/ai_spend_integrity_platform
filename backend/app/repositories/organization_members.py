"""Organization membership reads/writes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.models.organization import Organization
from app.models.organization_member import OrganizationMember, OrgMemberRole
from app.models.user import User


def get_membership(
    session: Session,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Optional[OrganizationMember]:
    """Load membership row for a user in an org, if any (includes deactivated)."""
    return session.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
    )


def is_active_member(member: OrganizationMember | None) -> bool:
    """True when the membership row grants org access."""
    return member is not None and member.deactivated_at is None


def get_active_membership(
    session: Session,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Optional[OrganizationMember]:
    """Active membership only (used for access checks)."""
    member = get_membership(session, organization_id=organization_id, user_id=user_id)
    return member if is_active_member(member) else None


def list_members_for_organization(
    session: Session,
    *,
    organization_id: uuid.UUID,
) -> list[OrganizationMember]:
    """All members (active + deactivated) for team roster UI."""
    rows = session.scalars(
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
        .options(
            joinedload(OrganizationMember.user),
            joinedload(OrganizationMember.deactivated_by),
        )
        .order_by(OrganizationMember.created_at.asc())
    ).all()
    return list(rows)


def count_active_org_admins(session: Session, *, organization_id: uuid.UUID) -> int:
    """Active org_admin count (prevent deactivating the last admin)."""
    from sqlalchemy import func

    return int(
        session.scalar(
            select(func.count())
            .select_from(OrganizationMember)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.role == OrgMemberRole.ORG_ADMIN.value,
                OrganizationMember.deactivated_at.is_(None),
            )
        )
        or 0
    )


def count_org_admins(session: Session, *, organization_id: uuid.UUID) -> int:
    """Backward-compatible alias for active org_admin count."""
    return count_active_org_admins(session, organization_id=organization_id)


def add_organization_member(
    session: Session,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
) -> OrganizationMember:
    """Insert membership; caller must ensure no duplicate and ``commit``."""
    row = OrganizationMember(
        organization_id=organization_id,
        user_id=user_id,
        role=role,
    )
    session.add(row)
    session.flush()
    return row


def update_member_role(
    session: Session,
    member: OrganizationMember,
    *,
    role: str,
) -> OrganizationMember:
    """Change org role (caller enforces admin rules)."""
    member.role = role
    session.flush()
    return member


def deactivate_organization_member(
    session: Session,
    member: OrganizationMember,
    *,
    deactivated_by_user_id: uuid.UUID,
) -> OrganizationMember:
    """Soft-remove: keep row for roster history; revoke org access."""
    member.deactivated_at = datetime.now(timezone.utc)
    member.deactivated_by_user_id = deactivated_by_user_id
    session.flush()
    return member


def remove_organization_member(session: Session, member: OrganizationMember) -> None:
    """Hard-delete membership row (prefer ``deactivate_organization_member``)."""
    session.delete(member)
    session.flush()


def list_organizations_for_member_user(
    session: Session,
    *,
    user_id: uuid.UUID,
    limit: int = 500,
) -> list[Organization]:
    """Orgs this user belongs to via ``organization_members`` (newest org first)."""
    rows = session.scalars(
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.deactivated_at.is_(None),
        )
        .order_by(Organization.created_at.desc())
        .limit(limit)
    ).all()
    return list(rows)
