"""HTTP response models for normalized ``bills`` / ``bill_line_items`` (read API)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BillLineItemResponse(BaseModel):
    """One persisted normalized line (2d output)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int = Field(..., description="Stable ordering within the bill.")
    raw_label: str
    canonical_line_kind: str
    canonical_service_key: Optional[str] = None
    quantity: Optional[Decimal] = None
    quantity_unit: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: str
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class BillResponse(BaseModel):
    """Normalized bill header + line items for the document viewer / clients."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    site_id: Optional[UUID] = None
    document_id: UUID
    raw_extraction_id: Optional[UUID] = None
    spend_domain: str
    spend_kind: Optional[str] = None
    issuer_name: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    currency: str
    total_amount: Optional[Decimal] = None
    summary: Optional[dict[str, Any]] = None
    normalization_version: str
    created_at: datetime
    updated_at: datetime
    line_items: list[BillLineItemResponse] = Field(default_factory=list)


class DocumentBillResponse(BaseModel):
    """Wrapper so clients can tell ``bill is null`` vs missing document (404)."""

    document_id: UUID
    bill: Optional[BillResponse] = None
