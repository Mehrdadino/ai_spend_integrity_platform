"""§3d persistence: write ``anomalies`` rows from §3b ``ComparisonFindingResponse`` objects.

Deleting prior rows for ``(bill_id, rule_pack_version)`` keeps the table aligned with reruns /
reprocessed bills without leaving stale fingerprints behind.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional, Sequence

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.anomaly import Anomaly
from app.models.bill import Bill
from app.schemas.comparison import ComparisonFindingResponse
from app.services.comparison.period import effective_period_end


def replace_anomalies_for_comparison(
    session: Session,
    *,
    current: Bill,
    compared_to_bill_id: Optional[uuid.UUID],
    findings: Sequence[ComparisonFindingResponse],
    rule_pack_version: str,
) -> None:
    """Delete existing snapshot rows then insert anomalies derived from ``findings``.

    ``current`` must be the normalized bill instance (rule pack callers load ``line_items``).

    Use a Core ``DELETE`` (no pre-load) when the session has not already attached ``Anomaly``
    rows for this bill—typical for ``GET …/bill/comparison``. That avoids loading rows into
    the identity map; ``Bill.anomalies`` uses ``passive_deletes`` so bill replacement does not
    emit invalid ``UPDATE anomalies SET bill_id = NULL``. Do **not** pair Core deletes with
    ``session.expire_all()`` (that expired the live ``Bill`` and led to bad flushes).
    """
    session.execute(
        delete(Anomaly).where(
            Anomaly.bill_id == current.id,
            Anomaly.rule_pack_version == rule_pack_version,
        )
    )

    rows = _flatten_findings_into_rows(
        current,
        findings,
        compared_to_bill_id,
        rule_pack_version,
    )
    session.add_all(rows)
    session.flush()


def _period_anchor(bill: Bill) -> Optional[date]:
    """Comparable billing-period date for uniqueness + UX (matches §3a ``effective_period_end``)."""
    return effective_period_end(bill)


def _flatten_findings_into_rows(
    current: Bill,
    findings: Sequence[ComparisonFindingResponse],
    compared_to_bill_id: Optional[uuid.UUID],
    rule_pack_version: str,
) -> list[Anomaly]:
    """Expand aggregate findings into ORM instances (notably **one row per new fee line**)."""
    anchor = _period_anchor(current)
    out: list[Anomaly] = []
    prior_id = compared_to_bill_id

    for finding in findings:
        if finding.rule_id == "new_fee_lines":
            rows = _expand_new_fee_lines(
                finding,
                current=current,
                compared_to=prior_id,
                period_anchor=anchor,
                rule_pack_version=rule_pack_version,
            )
            out.extend(rows)
            continue

        fp_prior = prior_id if finding.rule_id != "header_total_mismatch" else None
        fp = _base_fingerprint(
            finding.rule_id,
            current.id,
            compared_to=fp_prior,
            extra=None,
        )
        compared_col = prior_id if finding.rule_id == "mom_total_change" else None
        out.append(
            Anomaly(
                organization_id=current.organization_id,
                site_id=current.site_id,
                document_id=current.document_id,
                bill_id=current.id,
                bill_line_item_id=None,
                compared_to_bill_id=compared_col,
                rule_pack_version=rule_pack_version,
                rule_id=finding.rule_id,
                period_end=anchor,
                fingerprint=fp,
                severity=finding.severity,
                title=finding.title,
                summary=finding.summary,
                evidence=dict(finding.evidence),
                review_status="open",
            )
        )

    return out


def _expand_new_fee_lines(
    finding: ComparisonFindingResponse,
    *,
    current: Bill,
    compared_to: Optional[uuid.UUID],
    period_anchor: Optional[date],
    rule_pack_version: str,
) -> list[Anomaly]:
    fee_rows = finding.evidence.get("new_fee_lines")
    if not isinstance(fee_rows, list):
        fp = _base_fingerprint("new_fee_lines", current.id, compared_to=compared_to, extra="aggregate")
        return [
            Anomaly(
                organization_id=current.organization_id,
                site_id=current.site_id,
                document_id=current.document_id,
                bill_id=current.id,
                bill_line_item_id=None,
                compared_to_bill_id=compared_to,
                rule_pack_version=rule_pack_version,
                rule_id="new_fee_lines",
                period_end=period_anchor,
                fingerprint=fp,
                severity=finding.severity,
                title=finding.title,
                summary=finding.summary,
                evidence=dict(finding.evidence),
                review_status="open",
            )
        ]

    instances: list[Anomaly] = []
    for entry in fee_rows:
        if not isinstance(entry, dict):
            continue
        line_id_raw = entry.get("line_item_id")
        try:
            line_uuid = uuid.UUID(str(line_id_raw)) if line_id_raw is not None else None
        except (ValueError, TypeError):
            line_uuid = None
        fee_fp = str(entry.get("fingerprint") or "")
        fp = _base_fingerprint(
            "new_fee_line",
            current.id,
            compared_to=compared_to,
            extra=fee_fp or str(line_uuid or "unknown"),
        )
        ev: dict[str, Any] = {
            "parent_rule_id": "new_fee_lines",
            "prior_bill_id": finding.evidence.get("prior_bill_id"),
            "prior_period_end": finding.evidence.get("prior_period_end"),
            "line": entry,
        }
        summary_one = _single_fee_summary(entry)
        instances.append(
            Anomaly(
                organization_id=current.organization_id,
                site_id=current.site_id,
                document_id=current.document_id,
                bill_id=current.id,
                bill_line_item_id=line_uuid,
                compared_to_bill_id=compared_to,
                rule_pack_version=rule_pack_version,
                rule_id="new_fee_line",
                period_end=period_anchor,
                fingerprint=fp,
                severity=finding.severity,
                title="New fee line vs prior bill",
                summary=summary_one,
                evidence=ev,
                review_status="open",
            )
        )

    if not instances:
        fp = _base_fingerprint("new_fee_lines", current.id, compared_to=compared_to, extra="empty_expand")
        instances.append(
            Anomaly(
                organization_id=current.organization_id,
                site_id=current.site_id,
                document_id=current.document_id,
                bill_id=current.id,
                bill_line_item_id=None,
                compared_to_bill_id=compared_to,
                rule_pack_version=rule_pack_version,
                rule_id="new_fee_lines",
                period_end=period_anchor,
                fingerprint=fp,
                severity=finding.severity,
                title=finding.title,
                summary=finding.summary,
                evidence=dict(finding.evidence),
                review_status="open",
            )
        )

    return instances


def _single_fee_summary(entry: dict[str, Any]) -> str:
    label = entry.get("raw_label") or "Fee line"
    amt = entry.get("amount")
    cur = entry.get("currency") or ""
    if amt:
        return f"{label}: {amt} {cur}".strip()
    return str(label)


def _base_fingerprint(
    rule_id: str,
    current_bill_id: uuid.UUID,
    *,
    compared_to: Optional[uuid.UUID],
    extra: Optional[str],
) -> str:
    """Stable string for §3d unique indexes within a billing snapshot."""
    prior_part = str(compared_to) if compared_to is not None else "none"
    extra_part = f"|{extra}" if extra else ""
    return f"{rule_id}|{prior_part}|{current_bill_id}{extra_part}"
