"""Document upload HTTP API: presigned PUT and finalize (step 1b).

All routes require ``X-Organization-Id`` matching an organization UUID.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_organization
from app.db.session import get_db
from app.models.organization import Organization
from app.schemas.documents import (
    CompleteUploadResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
)
from app.services.upload_sessions import (
    complete_presigned_upload,
    create_presigned_upload,
)

router = APIRouter(prefix="/documents", tags=["documents"])


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
    db: Session = Depends(get_db),
    org: Organization = Depends(require_organization),
) -> CompleteUploadResponse:
    """After the client PUTs bytes to storage, finalize hash and size (server-side read)."""
    doc = complete_presigned_upload(db, organization_id=org.id, document_id=document_id)
    assert doc.sha256 is not None and doc.byte_size is not None
    return CompleteUploadResponse(
        document_id=doc.id,
        sha256=doc.sha256,
        byte_size=doc.byte_size,
        processing_status=doc.processing_status,
    )
