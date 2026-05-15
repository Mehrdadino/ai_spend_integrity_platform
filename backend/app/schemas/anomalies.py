"""§3d read models — persisted anomalies for dashboard / explorer UIs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AnomalyResponse(BaseModel):
    """Flattened anomaly for list/detail reads (explainability joins later §4)."""

    id: UUID
    organization_id: UUID
    site_id: Optional[UUID] = None
    site_name: Optional[str] = Field(None, description="Joined from ``sites.name`` when present.")
    document_id: UUID
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
    created_at: datetime
    updated_at: datetime
