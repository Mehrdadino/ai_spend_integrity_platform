"""Document HTTP API: list (1h), presigned upload, finalize, read-back, enqueue (1b–1d).

All routes require ``X-Organization-Id`` matching an organization UUID.

Static paths (``presigned-upload``) and sub-resources (``read-url``, ``viewer``, ``bill``,
``reprocess``) are registered before bare ``GET /{document_id}`` so path segments are not
parsed as UUIDs where inappropriate. The collection route ``GET ""`` must stay
before ``GET /{document_id}``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_organization
from app.config import get_settings
from app.db.session import get_db
from app.models.document import Document
from app.models.organization import Organization
from app.repositories.bills import get_bill_for_org_document
from app.repositories.document_raw_extractions import get_latest_raw_extraction_for_document
from app.repositories.documents import get_document_for_organization, list_documents_for_organization
from app.schemas.bills import BillResponse, DocumentBillResponse
from app.schemas.documents import (
    CompleteUploadResponse,
    DocumentDetailResponse,
    DocumentListItemResponse,
    DocumentReadUrlResponse,
    DocumentViewerResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
    RawExtractionSnapshotResponse,
    ReprocessDocumentResponse,
)
from app.services.document_pipeline_queue import enqueue_document_pipeline_safe
from app.services.document_read_urls import presigned_get_url_for_document
from app.services.document_reprocess import (
    ReprocessDocumentBadRequest,
    reprocess_document_for_organization,
)
from app.services.upload_sessions import (
    complete_presigned_upload,
    create_presigned_upload,
)

router = APIRouter(prefix="/documents", tags=["documents"])


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
        site_id=doc.site_id,
        bucket=doc.bucket,
        object_key=doc.object_key,
        sha256=doc.sha256,
        mime_type=doc.mime_type,
        byte_size=doc.byte_size,
        source=doc.source,
        processing_status=doc.processing_status,
        processing_error=doc.processing_error,
        created_at=doc.created_at,
        latest_raw_extraction=latest_snap,
    )


@router.get("", response_model=list[DocumentListItemResponse])
def get_documents(
    db: Session = Depends(get_db),
    org: Organization = Depends(require_organization),
    limit: int = Query(100, ge=1, le=500, description="Max rows returned (newest first)"),
) -> list[DocumentListItemResponse]:
    """List documents for the tenant (step 1h): ingestion / pipeline status overview."""
    rows = list_documents_for_organization(db, organization_id=org.id, limit=limit)
    return [
        DocumentListItemResponse(
            document_id=doc.id,
            site_id=doc.site_id,
            mime_type=doc.mime_type,
            byte_size=doc.byte_size,
            sha256=doc.sha256,
            source=doc.source,
            processing_status=doc.processing_status,
            processing_error=doc.processing_error,
            created_at=doc.created_at,
        )
        for doc in rows
    ]


@router.post("/presigned-upload", response_model=PresignedUploadResponse)
def post_presigned_upload(
    body: PresignedUploadRequest,
    db: Session = Depends(get_db),
    org: Organization = Depends(require_organization),
) -> PresignedUploadResponse:
    """Create a row in ``awaiting_object`` state and return a presigned PUT URL."""
    doc, upload_url, expires_in = create_presigned_upload(
        db,
        organization_id=org.id,
        site_id=body.site_id,
        mime_type=body.mime_type,
        expected_byte_size=body.expected_byte_size,
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
    org: Organization = Depends(require_organization),
) -> CompleteUploadResponse:
    """After the client PUTs bytes to storage, finalize hash and size (server-side read)."""
    doc = complete_presigned_upload(db, organization_id=org.id, document_id=document_id)
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
    org: Organization = Depends(require_organization),
) -> DocumentReadUrlResponse:
    """Presigned GET for the stored object; org-scoped; rejects unfinished uploads."""
    doc = get_document_for_organization(
        db, document_id=document_id, organization_id=org.id
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
    org: Organization = Depends(require_organization),
) -> DocumentViewerResponse:
    """Single response for viewer UI: metadata + presigned file URL (same org scope)."""
    doc = get_document_for_organization(
        db, document_id=document_id, organization_id=org.id
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
    org: Organization = Depends(require_organization),
) -> DocumentBillResponse:
    """Return the normalized bill for this document, or ``bill: null`` if not materialized yet."""
    doc = get_document_for_organization(
        db, document_id=document_id, organization_id=org.id
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    bill = get_bill_for_org_document(db, organization_id=org.id, document_id=document_id)
    if bill is None:
        return DocumentBillResponse(document_id=document_id, bill=None)
    return DocumentBillResponse(
        document_id=document_id,
        bill=BillResponse.model_validate(bill),
    )


@router.post("/{document_id}/reprocess", response_model=ReprocessDocumentResponse)
def post_reprocess_document(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    org: Organization = Depends(require_organization),
) -> ReprocessDocumentResponse:
    """Reset pipeline to ``queued`` and enqueue the worker (``extracted`` / ``failed`` / ``received`` / ``queued`` / ``pending``)."""
    try:
        doc = reprocess_document_for_organization(
            db, organization_id=org.id, document_id=document_id
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
    org: Organization = Depends(require_organization),
) -> DocumentDetailResponse:
    """Return one document scoped to the caller's org (for the upload UI detail link)."""
    doc = get_document_for_organization(
        db, document_id=document_id, organization_id=org.id
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _document_detail_response(db, doc)
