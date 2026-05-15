"""Build ``NormalizedBillDraft`` from ``document_raw_extractions`` rows (2c).

``build_normalized_bundle`` is version-dispatched: ``stub-v1`` and ``generic-bill-v1``
map line items into canonical kinds/units/service keys; unknown versions still
produce a minimal header-only bill so the worker does not crash before a mapper exists.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.constants.extraction import GENERIC_BILL_EXTRACTION_VERSION, STUB_EXTRACTION_VERSION
from app.constants.normalization import (
    NORM_VERSION,
    SPEND_DOMAIN_CONTRACT,
    SPEND_DOMAIN_TELECOM,
    SPEND_DOMAIN_UNSPECIFIED,
    SPEND_DOMAIN_UTILITY,
)
from app.models.document import Document
from app.models.document_raw_extraction import DocumentRawExtraction
from app.schemas.extraction.generic_bill_payload import GenericBillExtractionPayload
from app.schemas.extraction.stub_payload import StubRawExtractionPayload
from app.services.normalization.line_kind import infer_line_kind
from app.services.normalization.service_keys import infer_service_key
from app.services.normalization.units import canonicalize_quantity_unit

logger = logging.getLogger(__name__)


@dataclass
class NormalizedLineDraft:
    """One row to persist as ``BillLineItem`` (pre-ORM, pure data)."""

    position: int
    raw_label: str
    canonical_line_kind: str
    canonical_service_key: str | None
    quantity: Decimal | None
    quantity_unit: str | None
    amount: Decimal | None
    currency: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedBillDraft:
    """Header + lines to persist as ``Bill`` + ``BillLineItem`` rows."""

    spend_domain: str
    spend_kind: str | None
    total_amount: Decimal | None
    currency: str
    lines: list[NormalizedLineDraft]
    summary: dict[str, Any] = field(default_factory=dict)
    issuer_name: str | None = None
    period_start: date | None = None
    period_end: date | None = None


def _to_decimal(value: float | int | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def normalize_spend_domain(raw: str | None) -> str:
    """Map extraction hints to a coarse ``spend_domain`` bucket (extend over time)."""
    if not raw or not raw.strip():
        return SPEND_DOMAIN_UNSPECIFIED
    s = raw.strip().lower()
    mapping = {
        "unspecified": SPEND_DOMAIN_UNSPECIFIED,
        "unknown": SPEND_DOMAIN_UNSPECIFIED,
        "other": SPEND_DOMAIN_UNSPECIFIED,
        "utility": SPEND_DOMAIN_UTILITY,
        "utilities": SPEND_DOMAIN_UTILITY,
        "energy": SPEND_DOMAIN_UTILITY,
        "telecom": SPEND_DOMAIN_TELECOM,
        "internet": SPEND_DOMAIN_TELECOM,
        "broadband": SPEND_DOMAIN_TELECOM,
        "contract": SPEND_DOMAIN_CONTRACT,
        "vendor": SPEND_DOMAIN_CONTRACT,
        "saas": SPEND_DOMAIN_CONTRACT,
    }
    return mapping.get(s, SPEND_DOMAIN_UNSPECIFIED)


def _normalize_spend_kind(raw: str | None) -> str | None:
    if raw is None:
        return None
    t = raw.strip()
    if not t:
        return None
    return t.lower()[:128]


def _normalized_lines_from_drafts(draft_lines: Sequence[Any]) -> list[NormalizedLineDraft]:
    """Shared 2c line mapping for stub / generic line shapes (same attributes)."""
    lines: list[NormalizedLineDraft] = []
    for i, d in enumerate(draft_lines):
        qty = _to_decimal(getattr(d, "quantity", None))
        amt = _to_decimal(getattr(d, "amount", None))
        raw_label = str(getattr(d, "raw_label", ""))
        qunit = canonicalize_quantity_unit(getattr(d, "quantity_unit", None))
        line_kind = infer_line_kind(raw_label=raw_label, has_quantity=qty is not None)
        svc = infer_service_key(
            raw_label=raw_label,
            service_hint=getattr(d, "service_hint", None),
        )
        cur_raw = getattr(d, "currency", None) or "USD"
        cur = str(cur_raw).strip().upper()[:3] or "USD"
        extra: dict[str, Any] = {}
        hint = getattr(d, "service_hint", None)
        if hint:
            extra["service_hint"] = hint
        lines.append(
            NormalizedLineDraft(
                position=i,
                raw_label=raw_label,
                canonical_line_kind=line_kind,
                canonical_service_key=svc,
                quantity=qty,
                quantity_unit=qunit,
                amount=amt,
                currency=cur,
                extra=extra,
            )
        )
    return lines


def _totals_and_summary(
    *,
    document: Document,
    lines: list[NormalizedLineDraft],
    source_extraction_version: str,
    extra_summary: dict[str, Any] | None = None,
) -> tuple[Decimal | None, dict[str, Any]]:
    total_amount: Decimal | None = None
    if lines:
        acc = Decimal("0")
        any_amt = False
        for ln in lines:
            if ln.amount is not None:
                acc += ln.amount
                any_amt = True
        total_amount = acc if any_amt else None
    summary: dict[str, Any] = {
        "normalization": NORM_VERSION,
        "source_extraction_version": source_extraction_version,
        "document_mime_type": document.mime_type,
        "line_count": len(lines),
    }
    if extra_summary:
        summary.update(extra_summary)
    return total_amount, summary


def build_bundle_from_stub(document: Document, model: StubRawExtractionPayload) -> NormalizedBillDraft:
    """Normalize a validated ``stub-v1`` payload into a generic bill draft."""
    spend_domain = normalize_spend_domain(model.spend_domain)
    spend_kind = _normalize_spend_kind(model.spend_kind)
    currency = "USD"
    lines = _normalized_lines_from_drafts(model.draft_lines)
    total_amount, summary = _totals_and_summary(
        document=document,
        lines=lines,
        source_extraction_version=STUB_EXTRACTION_VERSION,
        extra_summary={"draft_line_count": len(model.draft_lines)},
    )
    return NormalizedBillDraft(
        spend_domain=spend_domain,
        spend_kind=spend_kind,
        total_amount=total_amount,
        currency=currency,
        lines=lines,
        summary=summary,
        issuer_name=None,
    )


def build_bundle_from_generic(document: Document, model: GenericBillExtractionPayload) -> NormalizedBillDraft:
    """Normalize a validated ``generic-bill-v1`` payload (LLM or deterministic)."""
    spend_domain = normalize_spend_domain(model.spend_domain)
    spend_kind = _normalize_spend_kind(model.spend_kind)
    currency = model.currency.upper()[:3]
    lines = _normalized_lines_from_drafts(model.lines)
    issuer = model.issuer_name.strip() if model.issuer_name and model.issuer_name.strip() else None
    total_amount, summary = _totals_and_summary(
        document=document,
        lines=lines,
        source_extraction_version=GENERIC_BILL_EXTRACTION_VERSION,
    )
    if issuer:
        summary["issuer_name"] = issuer
    if model.period_start is not None:
        summary["period_start"] = model.period_start.isoformat()
    if model.period_end is not None:
        summary["period_end"] = model.period_end.isoformat()
    return NormalizedBillDraft(
        spend_domain=spend_domain,
        spend_kind=spend_kind,
        total_amount=total_amount,
        currency=currency,
        lines=lines,
        summary=summary,
        issuer_name=issuer,
        period_start=model.period_start,
        period_end=model.period_end,
    )


def build_normalized_bundle(*, document: Document, raw_row: DocumentRawExtraction) -> NormalizedBillDraft:
    """Entry point for 2c: choose mapper from ``raw_row.extraction_version``."""
    v = raw_row.extraction_version or ""
    if v == STUB_EXTRACTION_VERSION:
        model = StubRawExtractionPayload.model_validate(raw_row.raw_payload)
        return build_bundle_from_stub(document, model)
    if v == GENERIC_BILL_EXTRACTION_VERSION:
        model = GenericBillExtractionPayload.model_validate(raw_row.raw_payload)
        return build_bundle_from_generic(document, model)

    logger.warning("normalization: no mapper for extraction_version=%r; header-only bill", v)
    return NormalizedBillDraft(
        spend_domain=SPEND_DOMAIN_UNSPECIFIED,
        spend_kind=None,
        total_amount=None,
        currency="USD",
        lines=[],
        summary={
            "normalization": NORM_VERSION,
            "unmapped_extraction_version": v,
            "document_mime_type": document.mime_type,
        },
        issuer_name=None,
    )
