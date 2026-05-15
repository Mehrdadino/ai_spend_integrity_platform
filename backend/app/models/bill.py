"""Normalized bill header per ``document`` (pillar 2d).

``spend_domain`` / ``spend_kind`` are intentionally **string** columns (not enums
in Postgres) so new verticals—water, broadband, SaaS contracts—ship as code + docs
without Alembic churn. Canonical vocabularies live in ``app.services.normalization``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from app.models.anomaly import Anomaly
    from app.models.bill_line_item import BillLineItem
    from app.models.document import Document
    from app.models.document_raw_extraction import DocumentRawExtraction
    from app.models.organization import Organization
    from app.models.site import Site

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Bill(Base):
    """One normalized bill snapshot for a single ingested ``document``."""

    __tablename__ = "bills"

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
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    raw_extraction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("document_raw_extractions.id", ondelete="SET NULL"),
        nullable=True,
    )
    spend_domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    spend_kind: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    issuer_name: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    period_start: Mapped[Optional[date]] = mapped_column(Date(), nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date(), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    normalization_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=_utc_now,
    )

    organization: Mapped["Organization"] = relationship("Organization", back_populates="bills")
    site: Mapped[Optional["Site"]] = relationship("Site", back_populates="bills")
    document: Mapped["Document"] = relationship("Document", back_populates="bill")
    raw_extraction: Mapped[Optional["DocumentRawExtraction"]] = relationship(
        "DocumentRawExtraction",
        back_populates="bills_from_this_extraction",
    )
    line_items: Mapped[list["BillLineItem"]] = relationship(
        "BillLineItem",
        back_populates="bill",
        cascade="all, delete-orphan",
        order_by="BillLineItem.position",
    )
    anomalies: Mapped[list["Anomaly"]] = relationship(
        "Anomaly",
        back_populates="bill",
        foreign_keys="Anomaly.bill_id",
    )
