"""Membership linking users to organizations with a per-tenant role."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OrgMemberRole(str, Enum):
    """Per-organization role (distinct from platform ``users.role``)."""

    ORG_ADMIN = "org_admin"
    MEMBER = "member"
    VIEWER = "viewer"


if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class OrganizationMember(Base):
    """A user belonging to an organization (team access; soft-deactivate via ``deactivated_at``)."""

    __tablename__ = "organization_members"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deactivated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="members",
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="organization_memberships",
        foreign_keys=[user_id],
    )
    deactivated_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[deactivated_by_user_id],
    )
