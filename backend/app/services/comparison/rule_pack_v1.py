"""§3b rule pack v1: deterministic MoM and line rules over normalized bills.

Compares the **current** bill to the **immediate prior** bill (first entry from §3a
``select_prior_bills``). Findings persist to ``anomalies`` when comparison runs (**§3d**).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence
from uuid import UUID

from app.constants.normalization import LINE_KIND_FEE
from app.models.bill import Bill
from app.models.bill_line_item import BillLineItem
from app.schemas.comparison import ComparisonFindingResponse, ComparisonSeverity
from app.services.comparison.line_match import fee_line_fingerprints, line_fingerprint
from app.services.comparison.period import effective_period_end
from app.services.comparison.rules_config import (
    HEADER_LINES_TOLERANCE,
    MOM_ABSOLUTE_WARNING,
    MOM_PERCENT_CRITICAL,
    MOM_PERCENT_WARNING,
    RULE_PACK_VERSION,
)
from app.services.comparison.formatting import format_money, format_percent
from app.services.comparison.single_bill_integrity import evaluate_single_bill_integrity


def _finding(
    *,
    rule_id: str,
    severity: ComparisonSeverity,
    title: str,
    summary: str,
    evidence: dict[str, Any] | None = None,
) -> ComparisonFindingResponse:
    return ComparisonFindingResponse(
        rule_id=rule_id,
        severity=severity,
        title=title,
        summary=summary,
        evidence=evidence or {},
    )


def _sum_line_amounts(lines: Sequence[BillLineItem]) -> Decimal | None:
    amounts = [li.amount for li in lines if li.amount is not None]
    if not amounts:
        return None
    total = Decimal("0")
    for amt in amounts:
        total += amt
    return total


def _mom_severity(delta: Decimal, prior_total: Decimal) -> ComparisonSeverity | None:
    """Return severity when MoM change exceeds thresholds, else ``None`` (no finding)."""
    abs_delta = abs(delta)
    if prior_total > 0:
        pct = (delta / prior_total) * Decimal("100")
        abs_pct = abs(pct)
        if abs_pct >= MOM_PERCENT_CRITICAL:
            return "critical"
        if abs_pct >= MOM_PERCENT_WARNING:
            return "warning"
        return None
    if abs_delta >= MOM_ABSOLUTE_WARNING:
        return "warning"
    return None


def _check_mom_total(current: Bill, prior: Bill) -> ComparisonFindingResponse | None:
    if current.total_amount is None or prior.total_amount is None:
        return None
    delta = current.total_amount - prior.total_amount
    severity = _mom_severity(delta, prior.total_amount)
    if severity is None:
        return None
    prior_total = prior.total_amount
    pct: Decimal | None = None
    if prior_total > 0:
        pct = (delta / prior_total) * Decimal("100")
    direction = "increased" if delta > 0 else "decreased"
    pct_part = f" ({format_percent(abs(pct))}%)" if pct is not None else ""
    return _finding(
        rule_id="mom_total_change",
        severity=severity,
        title="Month-over-month total change",
        summary=(
            f"Bill total {direction} by {format_money(abs(delta))} {current.currency}"
            f"{pct_part} vs the prior period."
        ),
        evidence={
            "current_total": format_money(current.total_amount),
            "prior_total": format_money(prior.total_amount),
            "delta_amount": format_money(delta),
            "delta_percent": float(format_percent(pct)) if pct is not None else None,
            "currency": current.currency,
            "prior_bill_id": str(prior.id),
            "prior_period_end": effective_period_end(prior).isoformat(),
        },
    )


def _check_header_total_mismatch(current: Bill) -> ComparisonFindingResponse | None:
    if current.total_amount is None:
        return None
    lines_sum = _sum_line_amounts(current.line_items)
    if lines_sum is None:
        return None
    diff = abs(current.total_amount - lines_sum)
    if diff <= HEADER_LINES_TOLERANCE:
        return None
    return _finding(
        rule_id="header_total_mismatch",
        severity="warning",
        title="Header total does not match line items",
        summary=(
            f"Bill header total ({format_money(current.total_amount)} {current.currency}) "
            f"differs from the sum of line amounts ({format_money(lines_sum)} {current.currency}) "
            f"by {format_money(diff)}."
        ),
        evidence={
            "header_total": format_money(current.total_amount),
            "lines_sum": format_money(lines_sum),
            "difference": format_money(diff),
            "currency": current.currency,
        },
    )


def _check_new_fee_lines(current: Bill, prior: Bill) -> ComparisonFindingResponse | None:
    prior_fps = fee_line_fingerprints(list(prior.line_items))
    new_fees: list[dict[str, Any]] = []
    for li in current.line_items:
        if li.canonical_line_kind != LINE_KIND_FEE:
            continue
        fp = line_fingerprint(li)
        if fp in prior_fps:
            continue
        new_fees.append(
            {
                "line_item_id": str(li.id),
                "raw_label": li.raw_label,
                "amount": format_money(li.amount) if li.amount is not None else None,
                "currency": li.currency,
                "fingerprint": fp,
            }
        )
    if not new_fees:
        return None
    count = len(new_fees)
    noun = "line" if count == 1 else "lines"
    return _finding(
        rule_id="new_fee_lines",
        severity="warning",
        title="New fee lines vs prior bill",
        summary=f"{count} fee {noun} on this bill did not appear on the immediate prior bill.",
        evidence={
            "prior_bill_id": str(prior.id),
            "prior_period_end": effective_period_end(prior).isoformat(),
            "new_fee_lines": new_fees,
            "count": count,
        },
    )


def evaluate_rule_pack_v1(
    *,
    current: Bill,
    priors: Sequence[Bill],
) -> tuple[list[ComparisonFindingResponse], UUID | None]:
    """Run all v1 rules; return findings and the prior bill id used for MoM (if any).

    ``header_total_mismatch`` runs on every bill (no prior required). MoM and new-fee rules
    need the immediate prior bill at the same ``site_id``.
    """
    findings: list[ComparisonFindingResponse] = []

    header_find = _check_header_total_mismatch(current)
    if header_find is not None:
        findings.append(header_find)

    findings.extend(evaluate_single_bill_integrity(current))

    if current.site_id is None:
        findings.append(
            _finding(
                rule_id="no_site_assigned",
                severity="info",
                title="No site assigned",
                summary="Assign a site to compare this bill to prior bills at the same location.",
            )
        )
        return findings, None

    if not priors:
        findings.append(
            _finding(
                rule_id="no_prior_bill",
                severity="info",
                title="First bill at this site (baseline)",
                summary=(
                    "This is the first bill we have for this location. Upload an older month at the "
                    "same site to enable month-over-month and new-fee comparisons. We still ran "
                    "single-bill integrity checks (header vs lines, duplicate lines, fee share, etc.)."
                ),
            )
        )
        return findings, None

    prior = priors[0]
    compared_id: UUID = prior.id

    mom_find = _check_mom_total(current, prior)
    if mom_find is not None:
        findings.append(mom_find)

    fee_find = _check_new_fee_lines(current, prior)
    if fee_find is not None:
        findings.append(fee_find)

    return findings, compared_id
