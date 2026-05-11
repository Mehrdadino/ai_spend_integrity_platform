"""Direct (server-side) document registration: upload bytes then insert a row.

Used by the ``register-document`` CLI and any path that already has the full
file in memory. For browser-scale files prefer the presigned two-step API
(``upload_sessions``) to avoid holding large bodies on the app server.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.document import Document
from app.services.storage import delete_document_object, put_document_object

logger = logging.getLogger(__name__)


class DuplicateDocumentError(Exception):
    """Raised when the same org already registered this exact file (SHA-256)."""

    def __init__(self, organization_id: uuid.UUID, sha256: str):
        self.organization_id = organization_id
        self.sha256 = sha256
        super().__init__(f"Duplicate document for org={organization_id} sha256={sha256}")


def register_document_bytes(
    session: Session,
    *,
    organization_id: uuid.UUID,
    site_id: Optional[uuid.UUID],
    body: bytes,
    mime_type: str,
    source: str = "upload",
    processing_status: str = "pending",
) -> Document:
    """Hash ``body``, write to S3, insert ``Document``; rollback S3 if DB flush fails.

    Order: duplicate check (DB) → PUT object → INSERT row, so we never claim a
    document exists without storage. On unique violation, delete the orphan key.
    """
    settings = get_settings()
    sha256 = hashlib.sha256(body).hexdigest()
    existing = session.scalar(
        select(Document).where(
            Document.organization_id == organization_id,
            Document.sha256 == sha256,
        )
    )
    if existing is not None:
        raise DuplicateDocumentError(organization_id, sha256)

    document_id = uuid.uuid4()
    bucket = settings.s3_bucket_documents
    # Key layout: {org_id}/{document_id} — stable and unique before insert.
    object_key = f"{organization_id}/{document_id}"

    put_document_object(bucket=bucket, key=object_key, body=body, content_type=mime_type)

    doc = Document(
        id=document_id,
        organization_id=organization_id,
        site_id=site_id,
        bucket=bucket,
        object_key=object_key,
        sha256=sha256,
        mime_type=mime_type,
        byte_size=len(body),
        source=source,
        processing_status=processing_status,
    )
    session.add(doc)
    try:
        session.flush()
    except IntegrityError:
        try:
            delete_document_object(bucket=bucket, key=object_key)
        except Exception:
            logger.exception(
                "Failed to remove S3 object after DB error: s3://%s/%s",
                bucket,
                object_key,
            )
        raise DuplicateDocumentError(organization_id, sha256) from None

    return doc
