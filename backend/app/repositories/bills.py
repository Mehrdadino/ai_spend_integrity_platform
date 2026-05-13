"""Bill + line-item reads scoped by ``organization_id`` (tenant safety)."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.bill import Bill
from app.models.document import Document


def get_bill_for_org_document(
    session: Session,
    *,
    organization_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Optional[Bill]:
    """Return ``Bill`` with ``line_items`` loaded, or ``None`` if missing or wrong org."""
    stmt = (
        select(Bill)
        .join(Document, Document.id == Bill.document_id)
        .where(
            Bill.document_id == document_id,
            Document.organization_id == organization_id,
        )
        .options(selectinload(Bill.line_items))
    )
    return session.scalar(stmt)
