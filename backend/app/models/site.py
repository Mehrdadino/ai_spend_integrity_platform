"""Site (e.g. store or facility) under an organization — optional scope for bills."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    # Forward refs for ORM relationship annotations without circular imports at runtime.
    from app.models.anomaly import Anomaly
    from app.models.bill import Bill
    from app.models.document import Document
    from app.models.organization import Organization


class Site(Base):
    """Physical or logical location; documents may attach for routing and UX."""

    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped["Organization"] = relationship("Organization", back_populates="sites")
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="site")
    bills: Mapped[list["Bill"]] = relationship("Bill", back_populates="site")
    anomalies: Mapped[list["Anomaly"]] = relationship("Anomaly", back_populates="site")
