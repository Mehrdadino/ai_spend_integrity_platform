"""§3b single-bill integrity rules (no prior bill required).

First-time users often upload one suspicious bill with no site history. These deterministic
checks inspect **this bill only**: duplicate lines, fee/tax share, penalty-style fees,
sparse period metadata, extraction provenance (``extraction_quality``), and utility/telecom
domain packs (``domain_packs``). Header-vs-lines math lives in ``rule_pack_v1``.
"""

from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal
from typing import Any, Sequence

from app.constants.normalization import LINE_KIND_CREDIT, LINE_KIND_FEE, LINE_KIND_TAX
from app.services.comparison.domain_packs import evaluate_domain_packs
from app.services.comparison.extraction_quality import evaluate_extraction_quality
from app.models.bill import Bill
from app.models.bill_line_item import BillLineItem
from app.schemas.comparison import ComparisonFindingResponse, ComparisonSeverity
from app.services.comparison.line_match import line_fingerprint
from app.services.comparison.formatting import format_money, format_percent
from app.services.comparison.rules_config import (
    FEES_SHARE_MIN_TOTAL,
    FEES_SHARE_WARNING_PCT,
    PENALTY_FEE_LABEL_PATTERN,
    TAX_SHARE_MIN_TOTAL,
    TAX_SHARE_WARNING_PCT,
)

_PENALTY_RE = re.compile(PENALTY_FEE_LABEL_PATTERN, re.IGNORECASE)


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


def _sum_amounts_for_kinds(lines: Sequence[BillLineItem], kinds: set[str]) -> Decimal:
    total = Decimal("0")
    for li in lines:
        if li.canonical_line_kind in kinds and li.amount is not None:
            total += li.amount
    return total


def _check_duplicate_line_fingerprints(
    lines: Sequence[BillLineItem],
    *,
    currency: str,
) -> ComparisonFindingResponse | None:
    """Flag repeated line fingerprints (possible double-billing on one invoice)."""
    counts: Counter[str] = Counter()
    amounts: dict[str, Decimal] = {}
    labels: dict[str, str] = {}
    for li in lines:
        if li.amount is None:
            continue
        fp = line_fingerprint(li)
        counts[fp] += 1
        amounts[fp] = amounts.get(fp, Decimal("0")) + li.amount
        labels[fp] = li.raw_label

    dupes = [(fp, n) for fp, n in counts.items() if n >= 2]
    if not dupes:
        return None
    dupes.sort(key=lambda x: (-x[1], x[0]))
    rows = [
        {
            "fingerprint": fp,
            "count": n,
            "combined_amount": format_money(amounts[fp]),
            "raw_label": labels.get(fp, ""),
        }
        for fp, n in dupes[:10]
    ]
    count = len(dupes)
    noun = "pattern" if count == 1 else "patterns"
    return _finding(
        rule_id="duplicate_line_fingerprint",
        severity="warning",
        title="Repeated line items on this bill",
        summary=(
            f"{count} line {noun} appear more than once with the same classification/label "
            f"({dupes[0][1]}× “{labels.get(dupes[0][0], 'line')}”). Review for duplicate charges."
        ),
        evidence={"duplicate_groups": rows, "currency": currency},
    )


def _check_fees_share_of_total(current: Bill) -> ComparisonFindingResponse | None:
    """Warn when fee lines are a large share of the bill total (common audit target)."""
    if current.total_amount is None or current.total_amount <= 0:
        return None
    if current.total_amount < FEES_SHARE_MIN_TOTAL:
        return None
    fee_sum = _sum_amounts_for_kinds(current.line_items, {LINE_KIND_FEE})
    if fee_sum <= 0:
        return None
    pct = (fee_sum / current.total_amount) * Decimal("100")
    if pct < FEES_SHARE_WARNING_PCT:
        return None
    return _finding(
        rule_id="fees_high_share_of_total",
        severity="warning",
        title="Fees are a large share of this bill",
        summary=(
            f"Fee lines sum to {format_money(fee_sum)} {current.currency} "
            f"({format_percent(pct)}% of the bill total {format_money(current.total_amount)} {current.currency}). "
            "Review riders, surcharges, and one-time fees."
        ),
        evidence={
            "fee_sum": format_money(fee_sum),
            "bill_total": format_money(current.total_amount),
            "fee_percent": float(format_percent(pct)),
            "currency": current.currency,
        },
    )


def _check_penalty_style_fees(lines: Sequence[BillLineItem], *, currency: str) -> ComparisonFindingResponse | None:
    """Surface late-payment / reconnect / penalty fees even without bill history."""
    hits: list[dict[str, Any]] = []
    for li in lines:
        if li.canonical_line_kind != LINE_KIND_FEE:
            continue
        if not _PENALTY_RE.search(li.raw_label):
            continue
        hits.append(
            {
                "line_item_id": str(li.id),
                "raw_label": li.raw_label,
                "amount": format_money(li.amount) if li.amount is not None else None,
            }
        )
    if not hits:
        return None
    return _finding(
        rule_id="penalty_style_fees",
        severity="warning",
        title="Penalty or late fees on this bill",
        summary=(
            f"{len(hits)} fee line(s) look like penalties, late payment, or reconnect charges. "
            "These are worth verifying even on a first upload."
        ),
        evidence={"fee_lines": hits, "count": len(hits), "currency": currency},
    )


def _check_missing_period_dates(current: Bill) -> ComparisonFindingResponse | None:
    """Data-quality signal when extraction did not capture a billing period."""
    if current.period_start is not None or current.period_end is not None:
        return None
    return _finding(
        rule_id="missing_period_dates",
        severity="info",
        title="Billing period not detected",
        summary=(
            "No service period start or end was extracted from this bill. "
            "Comparisons and period ordering work better when dates are present."
        ),
        evidence={},
    )


def _check_tax_share_of_total(current: Bill) -> ComparisonFindingResponse | None:
    """Warn when tax lines are a large share of the bill total (common audit target)."""
    if current.total_amount is None or current.total_amount <= 0:
        return None
    if current.total_amount < TAX_SHARE_MIN_TOTAL:
        return None
    tax_sum = _sum_amounts_for_kinds(current.line_items, {LINE_KIND_TAX})
    if tax_sum <= 0:
        return None
    pct = (tax_sum / current.total_amount) * Decimal("100")
    if pct < TAX_SHARE_WARNING_PCT:
        return None
    return _finding(
        rule_id="tax_high_share_of_total",
        severity="warning",
        title="Taxes are a large share of this bill",
        summary=(
            f"Tax lines sum to {format_money(tax_sum)} {current.currency} "
            f"({format_percent(pct)}% of the bill total {format_money(current.total_amount)} {current.currency}). "
            "Confirm tax jurisdiction lines were not misclassified as charges."
        ),
        evidence={
            "tax_sum": format_money(tax_sum),
            "bill_total": format_money(current.total_amount),
            "tax_percent": float(format_percent(pct)),
            "currency": current.currency,
        },
    )


def _check_credits_exceed_positive_charges(lines: Sequence[BillLineItem], *, currency: str) -> ComparisonFindingResponse | None:
    """Credits larger than non-credit charges may indicate a net credit bill or extraction issues."""
    credit_sum = abs(_sum_amounts_for_kinds(lines, {LINE_KIND_CREDIT}))
    if credit_sum <= 0:
        return None
    charge_sum = Decimal("0")
    for li in lines:
        if li.canonical_line_kind == LINE_KIND_CREDIT or li.amount is None:
            continue
        if li.amount > 0:
            charge_sum += li.amount
    if charge_sum <= 0:
        return None
    if credit_sum <= charge_sum:
        return None
    return _finding(
        rule_id="credits_exceed_charges",
        severity="warning",
        title="Credits exceed other charges on this bill",
        summary=(
            f"Credits total {format_money(credit_sum)} {currency} vs "
            f"{format_money(charge_sum)} {currency} in other positive lines. "
            "Confirm this is a net credit or adjustment bill."
        ),
        evidence={
            "credit_sum": format_money(credit_sum),
            "positive_non_credit_sum": format_money(charge_sum),
            "currency": currency,
        },
    )


def evaluate_single_bill_integrity(current: Bill) -> list[ComparisonFindingResponse]:
    """Run integrity rules that only need the current normalized bill."""
    findings: list[ComparisonFindingResponse] = []
    lines = list(current.line_items)
    currency = current.currency

    for check in (
        lambda: _check_duplicate_line_fingerprints(lines, currency=currency),
        lambda: _check_fees_share_of_total(current),
        lambda: _check_tax_share_of_total(current),
        lambda: _check_penalty_style_fees(lines, currency=currency),
        lambda: _check_missing_period_dates(current),
        lambda: _check_credits_exceed_positive_charges(lines, currency=currency),
    ):
        result = check()
        if result is not None:
            findings.append(result)

    findings.extend(evaluate_extraction_quality(current))
    findings.extend(evaluate_domain_packs(current))
    return findings
