"""§3d org-scoped anomaly list API (comparison findings persisted on compare)."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_organization
from app.db.session import get_db
from app.models.anomaly import Anomaly
from app.models.organization import Organization
from app.repositories.anomalies import list_anomalies_for_organization
from app.schemas.anomalies import AnomalyResponse

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get("", response_model=list[AnomalyResponse])
def list_anomalies(
    db: Session = Depends(get_db),
    org: Organization = Depends(require_organization),
    site_id: Optional[UUID] = Query(None, description="Optional ``sites.id`` filter (same-org)."),
    limit: int = Query(100, ge=1, le=500, description="Max rows (newest first)."),
) -> list[AnomalyResponse]:
    """Return persisted §3 comparison signals for dashboards (excluding soft-deleted documents)."""
    rows = list_anomalies_for_organization(
        db,
        organization_id=org.id,
        site_id=site_id,
        limit=limit,
    )
    return [_to_response(row) for row in rows]


def _to_response(row: Anomaly) -> AnomalyResponse:
    """Map ORM + optional ``site`` projection to HTTP model."""
    site_name = row.site.name if row.site is not None else None
    return AnomalyResponse(
        id=row.id,
        organization_id=row.organization_id,
        site_id=row.site_id,
        site_name=site_name,
        document_id=row.document_id,
        bill_id=row.bill_id,
        bill_line_item_id=row.bill_line_item_id,
        compared_to_bill_id=row.compared_to_bill_id,
        rule_pack_version=row.rule_pack_version,
        rule_id=row.rule_id,
        period_end=row.period_end,
        severity=row.severity,
        title=row.title,
        summary=row.summary,
        evidence=dict(row.evidence) if row.evidence is not None else {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
