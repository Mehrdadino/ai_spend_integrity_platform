"""Stored bill file metadata: pointer to S3 object, hash, MIME, pipeline status.

``sha256`` and ``byte_size`` may be null while a presigned upload is in flight;
a partial unique index enforces dedupe only once ``sha256`` is known (per org).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.site import Site

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utc_now() -> datetime:
    """Application-side ``updated_at`` bump (ORM ``onupdate``)."""
    return datetime.now(timezone.utc)


class Document(Base):
    """One uploaded or emailed file; object bytes live in the configured bucket."""

    __tablename__ = "documents"
    __table_args__ = (
        # Allow many in-flight uploads (sha256 NULL); enforce uniqueness once finalized.
        Index(
            "uq_documents_org_sha256_not_null",
            "organization_id",
            "sha256",
            unique=True,
            postgresql_where=text("sha256 IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    byte_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    # awaiting_object → queued (bytes ready) → received (worker ack, step 1d) → … extraction later.
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=_utc_now,
    )

    organization: Mapped[Organization] = relationship("Organization", back_populates="documents")
    site: Mapped[Optional[Site]] = relationship("Site", back_populates="documents")
