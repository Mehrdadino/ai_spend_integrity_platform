"""Organization (tenant) — top-level scope for sites, users, and documents."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Organization(Base):
    """A customer or pilot tenant. ``slug`` is stable for dev seeds and URLs."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sites: Mapped[list["Site"]] = relationship("Site", back_populates="organization")
    users: Mapped[list["User"]] = relationship("User", back_populates="organization")
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="organization")
