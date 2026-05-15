"""Transactional upsert of ``bills`` + ``bill_line_items`` from 2c drafts (2d).

Exactly one ``Bill`` row exists per ``document_id``; each successful pipeline run
replaces lines so reprocessing stays idempotent. Postgres stores bytes in S3;
this module only touches relational bill state scoped by ``document``.

When an existing bill row is replaced, ``session.delete`` relies on Postgres
``ON DELETE CASCADE`` into ``anomalies``; ``Bill.anomalies`` uses ``passive_deletes``
so SQLAlchemy does not emit ``UPDATE anomalies SET bill_id = NULL`` (``bill_id`` is
NOT NULL).
"""

from __future__ import annotations

import logging

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.normalization import NORM_VERSION
from app.models.bill import Bill
from app.models.bill_line_item import BillLineItem
from app.models.document import Document
from app.models.document_raw_extraction import DocumentRawExtraction
from app.services.normalization.from_extraction import build_normalized_bundle

logger = logging.getLogger(__name__)


def upsert_bill_for_document(
    session: Session,
    *,
    document: Document,
    raw_extraction: DocumentRawExtraction,
    summary_extra: dict[str, Any] | None = None,
) -> Bill:
    """Delete any prior bill for ``document``, insert header + line items from 2c."""
    bundle = build_normalized_bundle(document=document, raw_row=raw_extraction)
    if summary_extra:
        merged = dict(bundle.summary)
        merged.update(summary_extra)
        bundle.summary = merged

    existing = session.scalar(select(Bill).where(Bill.document_id == document.id))
    if existing is not None:
        session.delete(existing)
        session.flush()

    bill = Bill(
        organization_id=document.organization_id,
        site_id=document.site_id,
        document_id=document.id,
        raw_extraction_id=raw_extraction.id,
        spend_domain=bundle.spend_domain,
        spend_kind=bundle.spend_kind,
        issuer_name=bundle.issuer_name,
        period_start=bundle.period_start,
        period_end=bundle.period_end,
        currency=bundle.currency,
        total_amount=bundle.total_amount,
        summary=bundle.summary,
        normalization_version=NORM_VERSION,
    )

    for ln in bundle.lines:
        bill.line_items.append(
            BillLineItem(
                position=ln.position,
                raw_label=ln.raw_label,
                canonical_line_kind=ln.canonical_line_kind,
                canonical_service_key=ln.canonical_service_key,
                quantity=ln.quantity,
                quantity_unit=ln.quantity_unit,
                amount=ln.amount,
                currency=ln.currency,
                extra=dict(ln.extra),
            )
        )

    session.add(bill)
    session.flush()
    logger.info(
        "bill_sync: upserted bill document=%s lines=%s domain=%s",
        document.id,
        len(bundle.lines),
        bundle.spend_domain,
    )
    return bill
