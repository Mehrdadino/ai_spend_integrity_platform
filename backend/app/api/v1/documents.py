"""Document HTTP API: list (1h), presigned upload, finalize, read-back, enqueue (1b–1d).

Org-scoped routes require JWT bearer (P1) or dev ``X-Organization-Id`` when enabled.

Static paths (``presigned-upload``) and sub-resources (``read-url``, ``viewer``, ``bill``,
``bill/prior-bills``, ``bill/comparison``, ``reprocess``) are registered before bare ``GET /{document_id}`` so path segments are not
parsed as UUIDs where inappropriate. The collection route ``GET ""`` must stay
before ``GET /{document_id}``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_admin, require_auth_context, require_org_writer
from app.config import get_settings
from app.db.session import get_db
from app.models.document import Document
from app.repositories.bills import get_bill_for_org_document, get_prior_bills_for_org_document
from app.repositories.document_raw_extractions import get_latest_raw_extraction_for_document
from app.repositories.anomalies import review_status_by_document_ids
from app.repositories.documents import (
    browse_documents_for_organization,
    get_document_for_organization,
    list_documents_for_organization,
    update_document_display_name_for_organization,
)
from app.schemas.bills import BillResponse, DocumentBillResponse, DocumentPriorBillsResponse
from app.schemas.comparison import (
    DocumentComparisonResponse,
    PeerComparisonRequest,
    PeerSitesConfigResponse,
    SiteOptionResponse,
)
from app.services.comparison.evaluate import evaluate_document_comparison
from app.services.comparison.evaluate_peer import evaluate_document_peer_comparison
from app.services.comparison.peer_sites import read_saved_peer_site_ids
from app.repositories.sites import list_sites_for_organization
from app.services.comparison.period import BILL_ORDERING_NOTE
from app.services.document_site import DocumentSiteAssignmentError, assign_site_to_document
from app.schemas.documents import (
    CompleteUploadResponse,
    DocumentBrowseResponse,
    DocumentDetailResponse,
    DocumentListItemResponse,
    DocumentReadUrlResponse,
    DocumentViewerResponse,
    PatchDocumentDisplayNameRequest,
    PatchDocumentDisplayNameResponse,
    PatchDocumentSiteRequest,
    PatchDocumentSiteResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
    RawExtractionSnapshotResponse,
    DeleteDocumentResponse,
    ReprocessDocumentResponse,
)
from app.services.document_soft_delete import soft_delete_document
from app.services.comparison_queue import (
    enqueue_comparison_refresh_after_document_soft_delete,
    enqueue_document_comparison_backfill_safe,
    enqueue_site_comparison_refresh_safe,
)
from app.services.document_pipeline_queue import enqueue_document_pipeline_safe
from app.services.document_read_urls import presigned_get_url_for_document
from app.services.document_reprocess import (
    ReprocessDocumentBadRequest,
    reprocess_document_for_organization,
)
from app.services.upload_sessions import (
    DuplicateUploadError,
    complete_presigned_upload,
    create_presigned_upload,
    remove_awaiting_upload_placeholder,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def _document_list_items(
    db: Session,
    *,
    organization_id: UUID,
    rows: list[Document],
) -> list[DocumentListItemResponse]:
    """Map ORM rows to list DTOs with optional anomaly review rollup per document."""
    review_by_doc = review_status_by_document_ids(
        db,
        organization_id=organization_id,
        document_ids=[doc.id for doc in rows],
    )
    return [
        DocumentListItemResponse(
            document_id=doc.id,
            display_name=doc.display_name,
            site_id=doc.site_id,
            mime_type=doc.mime_type,
            byte_size=doc.byte_size,
            sha256=doc.sha256,
            source=doc.source,
            processing_status=doc.processing_status,
            processing_error=doc.processing_error,
            unsupported_reason_code=doc.unsupported_reason_code,
            unsupported_reason=doc.unsupported_reason,
            anomaly_review_status=review_by_doc.get(doc.id),
            created_at=doc.created_at,
        )
        for doc in rows
    ]


def _document_detail_response(db: Session, doc: Document) -> DocumentDetailResponse:
    """Map a ``Document`` ORM row + optional latest extraction to ``DocumentDetailResponse``."""
    latest = get_latest_raw_extraction_for_document(db, document_id=doc.id)
    latest_snap: RawExtractionSnapshotResponse | None = None
    if latest is not None:
        latest_snap = RawExtractionSnapshotResponse(
            extraction_id=latest.id,
            model_id=latest.model_id,
            extraction_version=latest.extraction_version,
            created_at=latest.created_at,
            raw_payload=dict(latest.raw_payload) if latest.raw_payload is not None else {},
        )
    return DocumentDetailResponse(
        document_id=doc.id,
        organization_id=doc.organization_id,
        display_name=doc.display_name,
        site_id=doc.site_id,
        bucket=doc.bucket,
        object_key=doc.object_key,
        sha256=doc.sha256,
        mime_type=doc.mime_type,
        byte_size=doc.byte_size,
        source=doc.source,
        processing_status=doc.processing_status,
        processing_error=doc.processing_error,
        unsupported_reason_code=doc.unsupported_reason_code,
        unsupported_reason=doc.unsupported_reason,
        created_at=doc.created_at,
        latest_raw_extraction=latest_snap,
    )


@router.get("", response_model=list[DocumentListItemResponse])
def get_documents(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
    limit: int = Query(100, ge=1, le=500, description="Max rows returned (newest first)"),
) -> list[DocumentListItemResponse]:
    """List documents for the tenant (step 1h): ingestion / pipeline status overview."""
    rows = list_documents_for_organization(db, organization_id=ctx.organization.id, limit=limit)
    return _document_list_items(db, organization_id=ctx.organization.id, rows=rows)


@router.get("/browse", response_model=DocumentBrowseResponse)
def browse_documents(
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
    q: str | None = Query(
        None,
        max_length=255,
        description="Optional filter: display name or document UUID fragment (case-insensitive).",
    ),
    offset: int = Query(0, ge=0, description="Pagination offset (newest documents first)."),
    limit: int = Query(20, ge=1, le=50, description="Page size (default 20)."),
) -> DocumentBrowseResponse:
    """Paginated document search for anomaly inbox and other pickers (scales to large orgs)."""
    rows, total = browse_documents_for_organization(
        db,
        organization_id=ctx.organization.id,
        q=q,
        offset=offset,
        limit=limit,
    )
    return DocumentBrowseResponse(
        items=_document_list_items(db, organization_id=ctx.organization.id, rows=rows),
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/presigned-upload", response_model=PresignedUploadResponse)
def post_presigned_upload(
    body: PresignedUploadRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_org_writer),
) -> PresignedUploadResponse:
    """Create a row in ``awaiting_object`` state and return a presigned PUT URL."""
    doc, upload_url, expires_in = create_presigned_upload(
        db,
        organization_id=ctx.organization.id,
        site_id=body.site_id,
        mime_type=body.mime_type,
        expected_byte_size=body.expected_byte_size,
        display_name=body.display_name,
    )
    return PresignedUploadResponse(
        document_id=doc.id,
        bucket=doc.bucket,
        object_key=doc.object_key,
        upload_url=upload_url,
        upload_method="PUT",
        # Client must echo this header on PUT or the signature will not match.
        headers={"Content-Type": body.mime_type},
        expires_in_seconds=expires_in,
    )


@router.post("/{document_id}/complete-upload", response_model=CompleteUploadResponse)
def post_complete_upload(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_org_writer),
) -> CompleteUploadResponse:
    """After the client PUTs bytes to storage, finalize hash and size (server-side read)."""
    try:
        doc = complete_presigned_upload(
            db, organization_id=ctx.organization.id, document_id=document_id
        )
    except DuplicateUploadError as exc:
        db.rollback()
        remove_awaiting_upload_placeholder(
            db,
            organization_id=ctx.organization.id,
            document_id=document_id,
        )
        return JSONResponse(
            status_code=409,
            content={
                "detail": (
                    "This file is already registered for this organization (duplicate SHA-256). "
                    "Delete the previous document first if you intended to replace it."
                ),
                "existing_document_id": str(exc.existing_document_id),
                "sha256": exc.sha256,
            },
        )
    assert doc.sha256 is not None and doc.byte_size is not None
    # Runs after ``get_db`` commits so the worker sees the final ``queued`` row.
    background_tasks.add_task(enqueue_document_pipeline_safe, doc.id)
    return CompleteUploadResponse(
        document_id=doc.id,
        sha256=doc.sha256,
        byte_size=doc.byte_size,
        processing_status=doc.processing_status,
        processing_error=doc.processing_error,
    )


@router.get("/{document_id}/read-url", response_model=DocumentReadUrlResponse)
def get_document_read_url(
    document_id: UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
) -> DocumentReadUrlResponse:
    """Presigned GET for the stored object; org-scoped; rejects unfinished uploads."""
    doc = get_document_for_organization(
        db, document_id=document_id, organization_id=ctx.organization.id
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    settings = get_settings()
    ttl = settings.presigned_read_expires_seconds
    try:
        url = presigned_get_url_for_document(doc, expires_in=ttl)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Document has no stored object yet (awaiting upload finalize)",
        )
    return DocumentReadUrlResponse(
        read_url=url,
        expires_in_seconds=ttl,
        mime_type=doc.mime_type,
    )


@router.get("/{document_id}/viewer", response_model=DocumentViewerResponse)
def get_document_viewer(
    document_id: UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
) -> DocumentViewerResponse:
    """Single response for viewer UI: metadata + presigned file URL (same org scope)."""
    doc = get_document_for_organization(
        db, document_id=document_id, organization_id=ctx.organization.id
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    detail = _document_detail_response(db, doc)
    settings = get_settings()
    ttl = settings.presigned_read_expires_seconds
    try:
        url = presigned_get_url_for_document(doc, expires_in=ttl)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Document has no stored object yet (awaiting upload finalize)",
        )
    return DocumentViewerResponse(
        **detail.model_dump(),
        read_url=url,
        read_url_expires_in_seconds=ttl,
    )


@router.get("/{document_id}/bill", response_model=DocumentBillResponse)
def get_document_bill(
    document_id: UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
) -> DocumentBillResponse:
    """Return the normalized bill for this document, or ``bill: null`` if not materialized yet."""
    doc = get_document_for_organization(
        db, document_id=document_id, organization_id=ctx.organization.id
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    bill = get_bill_for_org_document(db, organization_id=ctx.organization.id, document_id=document_id)
    if bill is None:
        return DocumentBillResponse(document_id=document_id, bill=None)
    return DocumentBillResponse(
        document_id=document_id,
        bill=BillResponse.model_validate(bill),
    )


@router.get("/{document_id}/bill/comparison", response_model=DocumentComparisonResponse)
def get_document_bill_comparison(
    document_id: UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
) -> DocumentComparisonResponse:
    """Run §3b rule pack v1 (MoM total, new fees, header mismatch) vs immediate prior bill."""
    doc = get_document_for_organization(
        db, document_id=document_id, organization_id=ctx.organization.id
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return evaluate_document_comparison(
        db,
        organization_id=ctx.organization.id,
        document_id=document_id,
    )


@router.get("/{document_id}/bill/peer-sites", response_model=PeerSitesConfigResponse)
def get_document_peer_sites_config(
    document_id: UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
) -> PeerSitesConfigResponse:
    """Return org sites and last saved peer-site picks for §3c (document viewer picker)."""
    doc = get_document_for_organization(
        db, document_id=document_id, organization_id=ctx.organization.id
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    bill = get_bill_for_org_document(
        db, organization_id=ctx.organization.id, document_id=document_id
    )
    site_rows = list_sites_for_organization(db, organization_id=ctx.organization.id, limit=500)
    return PeerSitesConfigResponse(
        document_id=document_id,
        anchor_site_id=doc.site_id,
        saved_peer_site_ids=read_saved_peer_site_ids(bill),
        available_sites=[SiteOptionResponse(id=s.id, name=s.name) for s in site_rows],
    )


@router.post("/{document_id}/bill/peer-comparison", response_model=DocumentComparisonResponse)
def post_document_peer_comparison(
    document_id: UUID,
    body: PeerComparisonRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_org_writer),
) -> DocumentComparisonResponse:
    """Run §3c peer pack for user-selected sites (or auto-discovery when ``peer_site_ids`` is empty)."""
    doc = get_document_for_organization(
        db, document_id=document_id, organization_id=ctx.organization.id
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.site_id is None:
        raise HTTPException(
            status_code=400,
            detail="Assign a site to this document before cross-site comparison.",
        )
    result = evaluate_document_peer_comparison(
        db,
        organization_id=ctx.organization.id,
        document_id=document_id,
        peer_site_ids=body.peer_site_ids,
    )
    db.commit()
    return result


@router.get("/{document_id}/bill/prior-bills", response_model=DocumentPriorBillsResponse)
def get_document_prior_bills(
    document_id: UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
    limit: int = Query(10, ge=1, le=50, description="Max prior bills to return (same site)."),
) -> DocumentPriorBillsResponse:
    """Return older normalized bills for the same ``site_id`` (§3a); empty when no site or no history."""
    doc = get_document_for_organization(
        db, document_id=document_id, organization_id=ctx.organization.id
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    current, priors = get_prior_bills_for_org_document(
        db,
        organization_id=ctx.organization.id,
        document_id=document_id,
        limit=limit,
    )
    return DocumentPriorBillsResponse(
        document_id=document_id,
        site_id=current.site_id if current else doc.site_id,
        current_bill_id=current.id if current else None,
        ordering_note=BILL_ORDERING_NOTE,
        prior_bills=[BillResponse.model_validate(b) for b in priors],
    )


@router.patch("/{document_id}/display-name", response_model=PatchDocumentDisplayNameResponse)
def patch_document_display_name(
    document_id: UUID,
    body: PatchDocumentDisplayNameRequest,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_org_writer),
) -> PatchDocumentDisplayNameResponse:
    """Set or clear the optional user label on a document (any pipeline status)."""
    doc = update_document_display_name_for_organization(
        db,
        document_id=document_id,
        organization_id=ctx.organization.id,
        display_name=body.display_name,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return PatchDocumentDisplayNameResponse(document_id=doc.id, display_name=doc.display_name)


@router.patch("/{document_id}/site", response_model=PatchDocumentSiteResponse)
def patch_document_site(
    document_id: UUID,
    body: PatchDocumentSiteRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_org_writer),
) -> PatchDocumentSiteResponse:
    """Assign a site to this document (and bill) for §3 historical comparison."""
    bill_before = get_bill_for_org_document(db, organization_id=ctx.organization.id, document_id=document_id)
    old_site_id = bill_before.site_id if bill_before is not None else None
    try:
        doc = assign_site_to_document(
            db,
            organization_id=ctx.organization.id,
            document_id=document_id,
            site_id=body.site_id,
        )
    except DocumentSiteAssignmentError as exc:
        status = 404 if "not found" in exc.detail.lower() else 400
        raise HTTPException(status_code=status, detail=exc.detail) from exc
    new_site_id = doc.site_id
    # §3e: backfill refreshes the bill's current site; also refresh the site it left.
    background_tasks.add_task(enqueue_document_comparison_backfill_safe, doc.id)
    if old_site_id is not None and old_site_id != new_site_id:
        background_tasks.add_task(
            enqueue_site_comparison_refresh_safe, ctx.organization.id, old_site_id
        )
    return PatchDocumentSiteResponse(document_id=doc.id, site_id=doc.site_id)


@router.delete("/{document_id}", response_model=DeleteDocumentResponse)
def delete_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_admin),
) -> DeleteDocumentResponse:
    """Soft-delete (org admin): set ``deleted_at``; S3 object remains until hard delete."""
    doc = soft_delete_document(
        db, organization_id=ctx.organization.id, document_id=document_id
    )
    if doc is None or doc.deleted_at is None:
        raise HTTPException(status_code=404, detail="Document not found")
    # §3e: neighbors' MoM / new-fee priors may have pointed at this bill; refresh the site chain.
    background_tasks.add_task(
        enqueue_comparison_refresh_after_document_soft_delete,
        ctx.organization.id,
        doc.site_id,
    )
    return DeleteDocumentResponse(document_id=doc.id, deleted_at=doc.deleted_at)


@router.post("/{document_id}/reprocess", response_model=ReprocessDocumentResponse)
def post_reprocess_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_org_writer),
) -> ReprocessDocumentResponse:
    """Reset pipeline to ``queued`` and enqueue the worker (``extracted`` / ``failed`` / ``received`` / ``queued`` / ``pending``)."""
    try:
        doc = reprocess_document_for_organization(
            db, organization_id=ctx.organization.id, document_id=document_id
        )
    except ReprocessDocumentBadRequest as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    background_tasks.add_task(enqueue_document_pipeline_safe, doc.id)
    return ReprocessDocumentResponse(
        document_id=doc.id,
        processing_status=doc.processing_status,
        processing_error=doc.processing_error,
    )


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    ctx: AuthContext = Depends(require_auth_context),
) -> DocumentDetailResponse:
    """Return one document scoped to the caller's org (for the upload UI detail link)."""
    doc = get_document_for_organization(
        db, document_id=document_id, organization_id=ctx.organization.id
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _document_detail_response(db, doc)
