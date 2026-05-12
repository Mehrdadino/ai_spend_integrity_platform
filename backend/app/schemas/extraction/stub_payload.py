"""Pydantic contract for the deterministic stub raw extraction (``stub-v1``).

``extra="forbid"`` rejects unknown keys so drift is caught early. ``model_dump`` is
what we persist to JSONB (canonical “image” of the validated object).
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StubRawExtractionPayload(BaseModel):
    """Shape produced by ``persist_stub_raw_extraction`` before frontier LLM wiring."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    stub: Literal[True]
    message: str = Field(..., min_length=1, max_length=4000)
    document_id: UUID
    mime_type: str = Field(..., min_length=1, max_length=255)
