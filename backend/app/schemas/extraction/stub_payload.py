"""Pydantic contract for the deterministic stub raw extraction (``stub-v1``).

``extra="forbid"`` rejects unknown keys so drift is caught early. ``model_dump`` is
what we persist to JSONB (canonical “image” of the validated object).

Optional ``draft_lines`` + ``spend_*`` hints exercise the **2c → 2d** path without a
frontier LLM; future real extractors should add new ``extraction_version`` models.
"""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StubDraftLine(BaseModel):
    """One synthetic line item for dev/tests (mirrors future LLM line shapes)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    raw_label: str = Field(..., min_length=1, max_length=2000)
    amount: Optional[float] = None
    currency: Optional[str] = Field(None, max_length=3)
    quantity: Optional[float] = None
    quantity_unit: Optional[str] = Field(None, max_length=64)
    service_hint: Optional[str] = Field(None, max_length=128)


class StubRawExtractionPayload(BaseModel):
    """Shape produced by ``persist_stub_raw_extraction`` before frontier LLM wiring."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    stub: Literal[True]
    message: str = Field(..., min_length=1, max_length=4000)
    document_id: UUID
    mime_type: str = Field(..., min_length=1, max_length=255)
    spend_domain: Optional[str] = Field(None, max_length=64)
    spend_kind: Optional[str] = Field(None, max_length=128)
    draft_lines: list[StubDraftLine] = Field(default_factory=list)
