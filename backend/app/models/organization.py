"""Organization (tenant) — top-level scope for sites, users, and documents."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    # Forward refs for SQLAlchemy relationship typing (Pyright); avoid runtime import cycles.
    from app.models.anomaly import Anomaly
    from app.models.anomaly_review_event import AnomalyReviewEvent
    from app.models.bill import Bill
    from app.models.document import Document
    from app.models.site import Site
    from app.models.user import User


class Organization(Base):
    """A customer or pilot tenant. ``slug`` is stable for dev seeds and URLs."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sites: Mapped[list["Site"]] = relationship("Site", back_populates="organization")
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="organization",
        foreign_keys="User.organization_id",
    )
    created_by: Mapped["User | None"] = relationship(
        "User",
        back_populates="organizations_created",
        foreign_keys=[created_by_user_id],
    )
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="organization")
    bills: Mapped[list["Bill"]] = relationship("Bill", back_populates="organization")
    anomalies: Mapped[list["Anomaly"]] = relationship("Anomaly", back_populates="organization")
    anomaly_review_events: Mapped[list["AnomalyReviewEvent"]] = relationship(
        "AnomalyReviewEvent",
        back_populates="organization",
    )
