"""Pydantic contract for ``generic-bill-v1`` raw extraction (LLM or deterministic).

``extra="forbid"`` keeps frontier models from drifting keys silently. This shape is
domain-agnostic: energy, water, telecom, and contract artifacts all use the same
line-item envelope; downstream 2c maps hints into canonical codes.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.extraction.period_dates import parse_bill_period_date


class GenericBillLineItem(BaseModel):
    """One extracted charge / usage row before 2c canonicalization."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    raw_label: str = Field(..., min_length=1, max_length=2000)
    amount: Optional[float] = None
    currency: Optional[str] = Field(None, max_length=3)
    quantity: Optional[float] = None
    quantity_unit: Optional[str] = Field(None, max_length=64)
    service_hint: Optional[str] = Field(None, max_length=128)


class GenericBillExtractionPayload(BaseModel):
    """Validated JSON stored in ``document_raw_extractions.raw_payload`` for ``generic-bill-v1``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    document_id: UUID
    spend_domain: Optional[str] = Field(None, max_length=64)
    spend_kind: Optional[str] = Field(None, max_length=128)
    issuer_name: Optional[str] = Field(None, max_length=500)
    currency: str = Field("USD", min_length=3, max_length=3)
    period_start: Optional[date] = Field(
        None,
        description="Billing period start (service interval) when stated on the bill.",
    )
    period_end: Optional[date] = Field(
        None,
        description="Billing period end or statement date when stated on the bill.",
    )
    lines: list[GenericBillLineItem] = Field(default_factory=list, max_length=500)

    @field_validator("period_start", "period_end", mode="before")
    @classmethod
    def coerce_period_dates(cls, v: Any) -> date | None:
        return parse_bill_period_date(v)

    @model_validator(mode="after")
    def period_end_not_before_start(self) -> "GenericBillExtractionPayload":
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_end < self.period_start
        ):
            raise ValueError("period_end must be on or after period_start")
        return self

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, v: Any) -> str:
        if v is None:
            return "USD"
        s = str(v).strip().upper()
        return (s[:3] if len(s) >= 3 else "USD") or "USD"
