"""§3d anomalies API; §4 explainability; §5 review transitions; batch §3 materialize (inbox Refresh)."""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_admin, require_auth_context
from app.db.session import get_db
from app.models.anomaly import Anomaly
from app.repositories.anomalies import (
    get_anomaly_for_organization,
    latest_review_notes_for_anomaly_ids,
    list_anomalies_for_organization,
    list_review_events_for_anomaly,
)
from app.schemas.anomalies import (
    AnomalyResponse,
    AnomalyReviewEventResponse,
    ExplainabilityResponse,
    MaterializeComparisonsResponse,
    ReviewTransitionRequest,
)
from app.services.explain import build_explainability_v1
from app.services.review import ReviewTransitionError, apply_review_transition
from app.services.comparison.limits import DEFAULT_SITE_BILL_SCAN
from app.services.comparison.materialize import materialize_comparisons_for_organization

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get("", response_model=list[AnomalyResponse])
def list_anomalies(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
    site_id: Optional[UUID] = Query(None, description="Optional ``sites.id`` filter (same-org)."),
    review_status: Optional[str] = Query(
        None,
        description="§5 filter: ``open`` | ``approved`` | ``dismissed`` | ``flagged``.",
    ),
    sort: Literal["created_at", "updated_at", "severity"] = Query(
        "created_at",
        description="Sort key (severity uses critical > warning > info).",
    ),
    order: Literal["asc", "desc"] = Query("desc"),
    limit: int = Query(100, ge=1, le=500, description="Max rows returned."),
) -> list[AnomalyResponse]:
    """Return persisted §3 comparison signals with §4 narratives and §5 review status."""
    rows = list_anomalies_for_organization(
        db,
        organization_id=ctx.organization.id,
        site_id=site_id,
        review_status=review_status,
        sort=sort,
        order=order,
        limit=limit,
    )
    notes = latest_review_notes_for_anomaly_ids(
        db,
        organization_id=ctx.organization.id,
        anomaly_ids=[row.id for row in rows],
    )
    return [_to_response(row, latest_review_note=notes.get(row.id)) for row in rows]


@router.post("/materialize-comparisons", response_model=MaterializeComparisonsResponse)
def post_materialize_comparisons(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
    site_id: Optional[UUID] = Query(
        None,
        description="Optional ``sites.id`` scope (match Anomalies list filter / Connection picker).",
    ),
    limit: int = Query(
        DEFAULT_SITE_BILL_SCAN,
        ge=1,
        le=500,
        description="Max documents to run comparison on.",
    ),
) -> MaterializeComparisonsResponse:
    """Run §3b comparison for every extracted document with a bill (inbox **Refresh** path).

    Same persistence as ``GET …/documents/{id}/bill/comparison`` per document; no viewer required.
    """
    ok, failed = materialize_comparisons_for_organization(
        db,
        organization_id=ctx.organization.id,
        site_id=site_id,
        limit=limit,
    )
    return MaterializeComparisonsResponse(
        attempted=len(ok) + len(failed),
        succeeded=len(ok),
        failed=len(failed),
    )


@router.post("/{anomaly_id}/review", response_model=AnomalyResponse)
def post_anomaly_review(
    anomaly_id: UUID,
    body: ReviewTransitionRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
) -> AnomalyResponse:
    """§5a: transition workflow state and append an audit row (§5b)."""
    row = get_anomaly_for_organization(
        db, organization_id=ctx.organization.id, anomaly_id=anomaly_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    try:
        apply_review_transition(
            db,
            anomaly=row,
            to_status=body.to_status,
            note=body.note,
            actor_user_id=ctx.user.id if ctx.user is not None else None,
        )
    except ReviewTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(row)
    notes = latest_review_notes_for_anomaly_ids(
        db,
        organization_id=ctx.organization.id,
        anomaly_ids=[row.id],
    )
    return _to_response(row, latest_review_note=notes.get(row.id))


@router.get("/{anomaly_id}/review-events", response_model=list[AnomalyReviewEventResponse])
def get_anomaly_review_events(
    anomaly_id: UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
) -> list[AnomalyReviewEventResponse]:
    """§5b: append-only history for one anomaly."""
    parent = get_anomaly_for_organization(
        db, organization_id=ctx.organization.id, anomaly_id=anomaly_id
    )
    if parent is None:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    events = list_review_events_for_anomaly(
        db,
        organization_id=ctx.organization.id,
        anomaly_id=anomaly_id,
    )
    return [
        AnomalyReviewEventResponse(
            id=e.id,
            anomaly_id=e.anomaly_id,
            from_status=e.from_status,
            to_status=e.to_status,
            note=e.note,
            actor_user_id=e.actor_user_id,
            created_at=e.created_at,
        )
        for e in events
    ]


@router.get("/{anomaly_id}", response_model=AnomalyResponse)
def get_anomaly(
    anomaly_id: UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
) -> AnomalyResponse:
    """Single anomaly read model (§4d + §5 status)."""
    row = get_anomaly_for_organization(
        db, organization_id=ctx.organization.id, anomaly_id=anomaly_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    notes = latest_review_notes_for_anomaly_ids(
        db,
        organization_id=ctx.organization.id,
        anomaly_ids=[row.id],
    )
    return _to_response(row, latest_review_note=notes.get(row.id))


def _to_response(row: Anomaly, *, latest_review_note: str | None = None) -> AnomalyResponse:
    """Map ORM row + template explainability to HTTP model."""
    site_name = row.site.name if row.site is not None else None
    ev = dict(row.evidence) if row.evidence is not None else {}
    ex = build_explainability_v1(
        rule_id=row.rule_id,
        severity=row.severity,
        evidence=ev,
        summary=row.summary,
    )
    rs = row.review_status
    if rs not in ("open", "approved", "dismissed", "flagged"):
        rs = "open"
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
        evidence=ev,
        explainability=ExplainabilityResponse(
            explanation=ex.explanation,
            confidence=ex.confidence,
            reasons=list(ex.reasons),
            version=ex.version,
        ),
        review_status=rs,  # type: ignore[arg-type]
        latest_review_note=latest_review_note,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
