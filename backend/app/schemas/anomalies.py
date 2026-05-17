"""§3d read models + §4 explainability + §5 review for dashboard APIs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

REVIEW_STATUS_LITERAL = Literal["open", "approved", "dismissed", "flagged"]


class ExplainabilityResponse(BaseModel):
    """§4 template narrative + confidence tier (grounded in ``evidence`` JSON only)."""

    explanation: str = Field(..., description="Plain-language paragraphs built from stored metrics.")
    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description="Heuristic data completeness / rule coverage (not statistical confidence).",
    )
    reasons: List[str] = Field(
        default_factory=list,
        description="Short phrases for tooltips or support (why this tier was chosen).",
    )
    version: str = Field(
        default="explain-v1",
        description="Template pack version; LLM polish would ship under a new label.",
    )


class ReviewTransitionRequest(BaseModel):
    """§5a body: move the anomaly to ``to_status`` and append an audit row."""

    to_status: REVIEW_STATUS_LITERAL
    note: Optional[str] = Field(
        None,
        max_length=8000,
        description="Optional note stored on the transition (§5e).",
    )


class AnomalyReviewEventResponse(BaseModel):
    """One append-only audit row from ``anomaly_review_events``."""

    id: UUID
    anomaly_id: UUID
    from_status: str
    to_status: str
    note: Optional[str] = None
    actor_user_id: Optional[UUID] = None
    created_at: datetime


class AnomalyResponse(BaseModel):
    """Flattened anomaly for list/detail reads including §4 explainability and §5 status."""

    id: UUID
    organization_id: UUID
    site_id: Optional[UUID] = None
    site_name: Optional[str] = Field(None, description="Joined from ``sites.name`` when present.")
    document_id: UUID
    document_display_name: Optional[str] = Field(
        None,
        description="Optional user label from ``documents.display_name`` (null when unset).",
    )
    bill_id: UUID
    bill_line_item_id: Optional[UUID] = None
    compared_to_bill_id: Optional[UUID] = None
    rule_pack_version: str
    rule_id: str
    period_end: Optional[date] = None
    severity: str
    title: str
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    explainability: ExplainabilityResponse
    review_status: REVIEW_STATUS_LITERAL
    latest_review_note: Optional[str] = Field(
        None,
        description="Most recent non-empty note from §5b audit events for this anomaly.",
    )
    created_at: datetime
    updated_at: datetime


class MaterializeComparisonsResponse(BaseModel):
    """Result of batch-running §3b comparison for extracted documents (inbox Refresh)."""

    attempted: int = Field(..., description="Documents considered (had bill + extracted status).")
    succeeded: int
    failed: int
