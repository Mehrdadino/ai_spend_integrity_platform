"""Presigned upload flow (step 1b): create DB row + URL, then finalize from S3.

Status flow: ``awaiting_object`` (client must PUT) → ``queued`` (bytes + hash
known; RQ worker step 1d moves to ``received``). Duplicate content per org is
blocked at finalize time via partial unique index on ``sha256``.
"""

from __future__ import annotations

import uuid
from typing import Optional

from botocore.exceptions import ClientError
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.document import Document
from app.repositories.documents import (
    get_document_by_organization_and_sha256,
    get_document_for_organization,
)
from app.repositories.sites import get_site_for_organization
from app.services.storage import generate_presigned_put_url, sha256_and_size_from_object

# Processing status strings (keep aligned with ``eng_roadmap`` / worker expectations).
PROCESSING_AWAITING_OBJECT = "awaiting_object"
PROCESSING_QUEUED = "queued"


class DuplicateUploadError(Exception):
    """Same file bytes already registered for this org (active row, not soft-deleted)."""

    def __init__(self, *, existing_document_id: uuid.UUID, sha256: str) -> None:
        self.existing_document_id = existing_document_id
        self.sha256 = sha256
        super().__init__(
            f"Duplicate SHA-256 for org; existing document_id={existing_document_id}"
        )


def remove_awaiting_upload_placeholder(
    session: Session,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
) -> bool:
    """Delete an unfinalized presigned-upload row (orphan after failed complete-upload)."""
    from sqlalchemy import select

    doc = session.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == organization_id,
            Document.processing_status == PROCESSING_AWAITING_OBJECT,
            Document.sha256.is_(None),
        )
    )
    if doc is None:
        return False
    session.delete(doc)
    session.flush()
    return True


def create_presigned_upload(
    session: Session,
    *,
    organization_id: uuid.UUID,
    site_id: Optional[uuid.UUID],
    mime_type: str,
    expected_byte_size: Optional[int],
) -> tuple[Document, str, int]:
    """Insert a placeholder ``Document`` and return a presigned PUT URL + TTL seconds.

    The client must PUT with header ``Content-Type`` exactly equal to ``mime_type``.
    """
    settings = get_settings()
    if expected_byte_size is not None and expected_byte_size > settings.max_upload_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"expected_byte_size exceeds max_upload_bytes ({settings.max_upload_bytes})",
        )
    if site_id is not None:
        site = get_site_for_organization(session, site_id, organization_id)
        if site is None:
            raise HTTPException(status_code=400, detail="site_id not found for this organization")

    document_id = uuid.uuid4()
    bucket = settings.s3_bucket_documents
    object_key = f"{organization_id}/{document_id}"

    doc = Document(
        id=document_id,
        organization_id=organization_id,
        site_id=site_id,
        bucket=bucket,
        object_key=object_key,
        sha256=None,
        mime_type=mime_type,
        byte_size=expected_byte_size,
        source="upload",
        processing_status=PROCESSING_AWAITING_OBJECT,
    )
    session.add(doc)
    session.flush()

    expires = settings.presigned_upload_expires_seconds
    url = generate_presigned_put_url(
        bucket=bucket,
        key=object_key,
        content_type=mime_type,
        expires_in=expires,
    )
    return doc, url, expires


def complete_presigned_upload(
    session: Session,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Document:
    """Read object from S3, compute hash/size, move row to ``queued``; 409 on duplicate hash."""
    settings = get_settings()
    doc = get_document_for_organization(
        session, document_id=document_id, organization_id=organization_id
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.processing_status != PROCESSING_AWAITING_OBJECT or doc.sha256 is not None:
        raise HTTPException(
            status_code=400,
            detail="Document is not waiting for an upload (wrong status or already finalized)",
        )

    try:
        sha256, size = sha256_and_size_from_object(bucket=doc.bucket, key=doc.object_key)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            raise HTTPException(
                status_code=400,
                detail="No object at storage path yet; PUT the file to upload_url first",
            ) from e
        raise

    if size == 0:
        raise HTTPException(status_code=400, detail="Empty uploads are not allowed")
    if size > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail="Uploaded object exceeds max_upload_bytes")

    existing = get_document_by_organization_and_sha256(
        session, organization_id=organization_id, sha256=sha256
    )
    if existing is not None:
        raise DuplicateUploadError(existing_document_id=existing.id, sha256=sha256)

    doc.sha256 = sha256
    doc.byte_size = size
    doc.processing_status = PROCESSING_QUEUED
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raced = get_document_by_organization_and_sha256(
            session, organization_id=organization_id, sha256=sha256
        )
        if raced is not None:
            raise DuplicateUploadError(existing_document_id=raced.id, sha256=sha256) from None
        raise HTTPException(
            status_code=409,
            detail="This file is already registered for this organization (duplicate SHA-256)",
        ) from None

    return doc
