"""One normalized charge / usage / adjustment line on a ``bill`` (pillar 2d).

``canonical_line_kind`` and ``canonical_service_key`` use **string** codes defined in
Python (see ``app.services.normalization``) so energy, water, telecom, and contract
artifacts can share one table shape.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from app.models.bill import Bill

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BillLineItem(Base):
    """Ordered line under ``bill_id``; ``extra`` holds domain-specific JSON (2c/2d)."""

    __tablename__ = "bill_line_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("bills.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer(), nullable=False)
    raw_label: Mapped[str] = mapped_column(Text(), nullable=False)
    canonical_line_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_service_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(24, 8), nullable=True)
    quantity_unit: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bill: Mapped["Bill"] = relationship("Bill", back_populates="line_items")
