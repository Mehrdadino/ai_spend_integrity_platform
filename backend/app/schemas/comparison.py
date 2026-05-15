"""HTTP models for §3b comparison findings (deterministic rule output persisted as §3d anomalies)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

ComparisonSeverity = Literal["info", "warning", "critical"]


class ComparisonFindingResponse(BaseModel):
    """One rule hit with grounded evidence (numbers, line ids, prior bill pointer)."""

    rule_id: str = Field(..., description="Stable id for §3d dedupe, e.g. mom_total_change.")
    severity: ComparisonSeverity
    title: str
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class DocumentComparisonResponse(BaseModel):
    """Rule-pack output for a document's current normalized bill vs its immediate prior."""

    document_id: UUID
    bill_id: Optional[UUID] = None
    site_id: Optional[UUID] = None
    rule_pack_version: str
    compared_to_bill_id: Optional[UUID] = Field(
        None,
        description="Immediate prior bill used for MoM / line rules (§3a ordering).",
    )
    compared_to_period_end: Optional[date] = None
    findings: list[ComparisonFindingResponse] = Field(default_factory=list)
