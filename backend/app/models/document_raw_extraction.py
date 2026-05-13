"""Append-only LLM output rows for a document (pillar 2a).

Each insert is a versioned snapshot: ``raw_payload`` is JSONB (arbitrary object).
Downstream normalization (2b–2d) reads the latest row or walks history. ``Bill`` rows
may reference a snapshot via ``raw_extraction_id`` for lineage.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from app.models.bill import Bill
    from app.models.document import Document

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DocumentRawExtraction(Base):
    """One persisted LLM (or stub) extraction for ``document_id``."""

    __tablename__ = "document_raw_extractions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    model_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    extraction_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["Document"] = relationship("Document", back_populates="raw_extractions")
    bills_from_this_extraction: Mapped[list["Bill"]] = relationship(
        "Bill",
        back_populates="raw_extraction",
    )
