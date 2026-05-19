"""User account — platform login, global email, optional home org (P1/P3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PlatformRole(str, Enum):
    """Platform-wide role: admins see all orgs; members only orgs they created."""

    ADMIN = "admin"
    MEMBER = "member"


# Backward-compatible alias for imports that still say UserRole.
UserRole = PlatformRole

if TYPE_CHECKING:
    from app.models.anomaly_review_event import AnomalyReviewEvent
    from app.models.auth_challenge import AuthChallenge
    from app.models.organization import Organization
    from app.models.organization_member import OrganizationMember


class User(Base):
    """Login identity. ``email`` is globally unique; ``role`` is platform admin vs member."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=PlatformRole.MEMBER.value)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization",
        back_populates="users",
        foreign_keys=[organization_id],
    )
    anomaly_review_events: Mapped[list["AnomalyReviewEvent"]] = relationship(
        "AnomalyReviewEvent",
        back_populates="actor",
    )
    organizations_created: Mapped[list["Organization"]] = relationship(
        "Organization",
        back_populates="created_by",
        foreign_keys="Organization.created_by_user_id",
    )
    auth_challenges: Mapped[list["AuthChallenge"]] = relationship(
        "AuthChallenge",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    organization_memberships: Mapped[list["OrganizationMember"]] = relationship(
        "OrganizationMember",
        back_populates="user",
        cascade="all, delete-orphan",
    )
