"""§3d anomaly rows: deterministic comparison findings anchored to normalized bills."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from app.models.anomaly_review_event import AnomalyReviewEvent
    from app.models.bill import Bill
    from app.models.bill_line_item import BillLineItem
    from app.models.document import Document
    from app.models.organization import Organization
    from app.models.site import Site

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Anomaly(Base):
    """One surfaced comparison signal for a normalized ``Bill`` (from §3b rule packs).

    Reruns of comparison upsert rows for ``(bill_id, rule_pack_version)`` by ``fingerprint`` so
    metrics refresh but §5 ``review_status`` (and audit events) survive when the finding is unchanged.
    """

    __tablename__ = "anomalies"

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
        index=True,
    )
    bill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("bills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bill_line_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("bill_line_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    compared_to_bill_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("bills.id", ondelete="SET NULL"),
        nullable=True,
    )
    rule_pack_version: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    period_end: Mapped[Optional[date]] = mapped_column(Date(), nullable=True, index=True)
    fingerprint: Mapped[str] = mapped_column(String(512), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text(), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=_utc_now,
    )

    organization: Mapped["Organization"] = relationship("Organization", back_populates="anomalies")
    site: Mapped[Optional["Site"]] = relationship("Site", back_populates="anomalies")
    document: Mapped["Document"] = relationship("Document", back_populates="anomalies")
    bill: Mapped["Bill"] = relationship(
        "Bill",
        foreign_keys=[bill_id],
        back_populates="anomalies",
    )
    compared_to_bill: Mapped[Optional["Bill"]] = relationship(
        "Bill",
        foreign_keys=[compared_to_bill_id],
    )
    line_item: Mapped[Optional["BillLineItem"]] = relationship(
        "BillLineItem",
        foreign_keys=[bill_line_item_id],
    )
    review_events: Mapped[list["AnomalyReviewEvent"]] = relationship(
        "AnomalyReviewEvent",
        back_populates="anomaly",
        order_by="AnomalyReviewEvent.created_at",
        passive_deletes=True,
    )
