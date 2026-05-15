"""Assign ``documents.site_id`` and keep ``bills.site_id`` in sync (UI / API)."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.document import Document
from app.repositories.bills import get_bill_for_org_document
from app.repositories.documents import get_document_for_organization
from app.repositories.sites import get_site_for_organization


class DocumentSiteAssignmentError(Exception):
    """Raised when site or document is invalid for the org."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def assign_site_to_document(
    session: Session,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
    site_id: Optional[uuid.UUID],
) -> Document:
    """Set ``site_id`` on the document and its normalized bill (if any)."""
    doc = get_document_for_organization(
        session, document_id=document_id, organization_id=organization_id
    )
    if doc is None:
        raise DocumentSiteAssignmentError("Document not found")

    if site_id is not None:
        site = get_site_for_organization(session, site_id, organization_id)
        if site is None:
            raise DocumentSiteAssignmentError("site_id not found for this organization")

    doc.site_id = site_id
    bill = get_bill_for_org_document(
        session, organization_id=organization_id, document_id=document_id
    )
    if bill is not None:
        bill.site_id = site_id
    session.flush()
    return doc
