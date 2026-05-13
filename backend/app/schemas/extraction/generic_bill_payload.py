"""Pydantic contract for ``generic-bill-v1`` raw extraction (LLM or deterministic).

``extra="forbid"`` keeps frontier models from drifting keys silently. This shape is
domain-agnostic: energy, water, telecom, and contract artifacts all use the same
line-item envelope; downstream 2c maps hints into canonical codes.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    lines: list[GenericBillLineItem] = Field(default_factory=list, max_length=500)

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, v: Any) -> str:
        if v is None:
            return "USD"
        s = str(v).strip().upper()
        return (s[:3] if len(s) >= 3 else "USD") or "USD"
