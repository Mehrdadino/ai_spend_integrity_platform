"""HTTP webhook for inbound email → document storage + pipeline enqueue (1e–1g).

URL embeds ``Organization.ingest_email_token`` so tenancy does not depend on
provider-supplied org headers. Optional Mailgun signature and/or a static
request header gate mis-posts when configured.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import get_settings
from app.repositories.documents import get_document_by_organization_and_sha256
from app.repositories.organizations import get_organization_by_ingest_email_token
from app.repositories.sites import get_site_for_organization
from app.schemas.inbound_email import InboundEmailDocumentResult, InboundEmailWebhookResponse
from app.services.document_pipeline_queue import enqueue_document_pipeline_safe
from app.services.document_registry import DuplicateDocumentError, register_document_bytes
from app.services.inbound_email import (
    collect_pdf_attachments_from_form,
    combine_recipient_hints,
    enforce_inbound_email_security,
    extract_site_uuid_from_recipient_text,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/inbound-email/{ingest_token}",
    response_model=InboundEmailWebhookResponse,
    summary="Inbound email (multipart) → PDF documents",
)
async def post_inbound_email(
    ingest_token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> InboundEmailWebhookResponse:
    """Accept SendGrid/Mailgun-style multipart POST and register each PDF attachment."""
    settings = get_settings()
    org = get_organization_by_ingest_email_token(db, ingest_token)
    if org is None or not org.ingest_email_token:
        raise HTTPException(status_code=404, detail="Unknown ingest token")

    form = await request.form()
    plain, pdf_parts = await collect_pdf_attachments_from_form(form)

    err = enforce_inbound_email_security(settings=settings, plain=plain, headers=request.headers)
    if err:
        raise HTTPException(status_code=401, detail=err)

    recipient_blob = combine_recipient_hints(plain)
    site_id: Optional[UUID] = None
    hinted = extract_site_uuid_from_recipient_text(recipient_blob)
    if hinted is not None:
        site = get_site_for_organization(db, hinted, org.id)
        if site is None:
            logger.warning(
                "Inbound email site hint %s not found for org %s; ingesting without site",
                hinted,
                org.id,
            )
        else:
            site_id = site.id

    if not pdf_parts:
        raise HTTPException(
            status_code=422,
            detail="No PDF attachments found (expected SendGrid attachmentN, Mailgun body-mime, or file parts)",
        )

    max_n = max(1, settings.inbound_email_max_documents_per_request)
    pdf_parts = pdf_parts[:max_n]

    results: list[InboundEmailDocumentResult] = []
    for filename, mime_type, body in pdf_parts:
        if len(body) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Attachment {filename!r} exceeds max_upload_bytes ({settings.max_upload_bytes})",
            )
        try:
            with db.begin_nested():
                doc = register_document_bytes(
                    db,
                    organization_id=org.id,
                    site_id=site_id,
                    body=body,
                    mime_type=mime_type or "application/pdf",
                    source="email",
                    processing_status="queued",
                )
            results.append(InboundEmailDocumentResult(document_id=doc.id, outcome="created"))
        except DuplicateDocumentError as dup:
            existing = get_document_by_organization_and_sha256(
                db, organization_id=dup.organization_id, sha256=dup.sha256
            )
            if existing is None:
                logger.error("DuplicateDocumentError but no row for org=%s sha256=%s", dup.organization_id, dup.sha256)
                raise HTTPException(status_code=500, detail="Duplicate document state inconsistent") from dup
            results.append(InboundEmailDocumentResult(document_id=existing.id, outcome="duplicate"))

    db.commit()
    for r in results:
        if r.outcome == "created":
            background_tasks.add_task(enqueue_document_pipeline_safe, r.document_id)

    return InboundEmailWebhookResponse(results=results)


@router.head("/inbound-email/{ingest_token}")
def head_inbound_email(_ingest_token: str) -> Response:
    """Some providers probe the URL; acknowledge without parsing a body."""
    return Response(status_code=200)
