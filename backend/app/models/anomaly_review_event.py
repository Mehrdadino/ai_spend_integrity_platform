"""§5b append-only audit rows for anomaly review state changes (tenant + anomaly scoped)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.anomaly import Anomaly
    from app.models.organization import Organization
    from app.models.user import User


class AnomalyReviewEvent(Base):
    """One transition ``from_status`` → ``to_status`` written when a reviewer acts (§5a/§5e).

    ``actor_user_id`` is optional until real auth attaches an end-user; tenant safety is
    ``organization_id`` + ``anomaly_id``.
    """

    __tablename__ = "anomaly_review_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    anomaly_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("anomalies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped["Organization"] = relationship("Organization", back_populates="anomaly_review_events")
    anomaly: Mapped["Anomaly"] = relationship("Anomaly", back_populates="review_events")
    actor: Mapped[Optional["User"]] = relationship("User", back_populates="anomaly_review_events")
