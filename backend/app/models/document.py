"""Stored bill file metadata: pointer to S3 object, hash, MIME, pipeline status.

``sha256`` and ``byte_size`` may be null while a presigned upload is in flight;
a partial unique index enforces dedupe only once ``sha256`` is known (per org).

``processing_error`` is set when the worker marks ``failed``; cleared when a new
``queued`` job is processed successfully. ``raw_extractions`` holds pillar **2a**
JSONB blobs (append-only).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.models.anomaly import Anomaly
    from app.models.bill import Bill
    from app.models.document_raw_extraction import DocumentRawExtraction
    from app.models.organization import Organization
    from app.models.site import Site

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
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
    """One uploaded file; object bytes live in the configured bucket."""

    __tablename__ = "documents"
    __table_args__ = (
        # Allow many in-flight uploads (sha256 NULL); dedupe active rows only (soft-deleted excluded).
        Index(
            "uq_documents_org_sha256_active",
            "organization_id",
            "sha256",
            unique=True,
            postgresql_where=text("sha256 IS NOT NULL AND deleted_at IS NULL"),
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
    # awaiting_object → queued → received → extracted | failed (worker-driven).
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    # Worker/API failure summary for ingestion list UI (cleared on successful retry).
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Soft delete: set by DELETE API; excluded from list/viewer queries until hard delete exists.
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=_utc_now,
    )

    organization: Mapped[Organization] = relationship("Organization", back_populates="documents")
    site: Mapped[Optional[Site]] = relationship("Site", back_populates="documents")
    raw_extractions: Mapped[list["DocumentRawExtraction"]] = relationship(
        "DocumentRawExtraction",
        back_populates="document",
        cascade="all, delete-orphan",
    )
    bill: Mapped[Optional["Bill"]] = relationship(
        "Bill",
        back_populates="document",
        uselist=False,
    )
    anomalies: Mapped[list["Anomaly"]] = relationship("Anomaly", back_populates="document")
