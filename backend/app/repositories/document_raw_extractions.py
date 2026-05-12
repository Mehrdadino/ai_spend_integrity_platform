"""Queries for ``document_raw_extractions`` (pillar 2a): latest snapshot per document."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document_raw_extraction import DocumentRawExtraction


def get_latest_raw_extraction_for_document(
    session: Session,
    *,
    document_id: uuid.UUID,
) -> Optional[DocumentRawExtraction]:
    """Return the newest row for ``document_id`` (by ``created_at``), or None."""
    return session.scalar(
        select(DocumentRawExtraction)
        .where(DocumentRawExtraction.document_id == document_id)
        .order_by(DocumentRawExtraction.created_at.desc())
        .limit(1)
    )
