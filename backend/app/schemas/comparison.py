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
    peer_site_ids_used: list[UUID] = Field(
        default_factory=list,
        description="§3c: peer sites used for this run (empty = automatic discovery).",
    )


class PeerComparisonRequest(BaseModel):
    """User-selected sites to compare against the anchor bill (§3c)."""

    peer_site_ids: list[UUID] = Field(
        default_factory=list,
        description="Other sites in this org; empty = automatic peer discovery.",
    )


class SiteOptionResponse(BaseModel):
    """Minimal site row for the cross-site peer picker."""

    id: UUID
    name: str


class PeerSitesConfigResponse(BaseModel):
    """Saved peer-site picker state + org sites list for the document viewer."""

    document_id: UUID
    anchor_site_id: Optional[UUID] = None
    saved_peer_site_ids: list[UUID] = Field(default_factory=list)
    available_sites: list[SiteOptionResponse] = Field(default_factory=list)
