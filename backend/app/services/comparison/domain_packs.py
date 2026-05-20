"""§3b utility-domain packs: electric / gas / water heuristics on normalized lines.

These are **single-bill** checks (no prior) keyed off ``spend_kind``, service keys, and
line labels/units. They complement generic integrity rules in ``single_bill_integrity``.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Sequence

from app.constants.normalization import (
    LINE_KIND_CHARGE,
    LINE_KIND_FEE,
    LINE_KIND_USAGE,
    SPEND_DOMAIN_TELECOM,
    SPEND_DOMAIN_UTILITY,
    UNIT_CCF,
    UNIT_GALLON,
    UNIT_KWH,
    UNIT_LITER,
    UNIT_THERM,
)
from app.models.bill import Bill
from app.models.bill_line_item import BillLineItem
from app.schemas.comparison import ComparisonFindingResponse
from app.services.normalization.service_keys import (
    SERVICE_UTILITY_ELECTRIC,
    SERVICE_UTILITY_NATURAL_GAS,
    SERVICE_UTILITY_WATER,
)

_DEMAND_LABEL_RE = re.compile(r"\bdemand\b", re.IGNORECASE)
_KW_NOT_KWH_RE = re.compile(r"\bkw\b(?!\s*h)", re.IGNORECASE)
_KWH_RE = re.compile(r"\bkwh\b", re.IGNORECASE)

_WATER_UNITS = frozenset({UNIT_GALLON, UNIT_CCF, UNIT_LITER})
_GAS_UNITS = frozenset({UNIT_THERM, UNIT_CCF})


def _finding(
    *,
    rule_id: str,
    title: str,
    summary: str,
    evidence: dict[str, Any] | None = None,
) -> ComparisonFindingResponse:
    return ComparisonFindingResponse(
        rule_id=rule_id,
        severity="warning",
        title=title,
        summary=summary,
        evidence=evidence or {},
    )


def _spend_kind_lower(bill: Bill) -> str:
    return (bill.spend_kind or "").strip().lower()


def _bill_looks_electric(bill: Bill, lines: Sequence[BillLineItem]) -> bool:
    sk = _spend_kind_lower(bill)
    if "electric" in sk or "power" in sk or sk == "electricity":
        return True
    return any(li.canonical_service_key == SERVICE_UTILITY_ELECTRIC for li in lines)


def _bill_looks_gas(bill: Bill, lines: Sequence[BillLineItem]) -> bool:
    sk = _spend_kind_lower(bill)
    if "gas" in sk or "natural" in sk:
        return True
    return any(li.canonical_service_key == SERVICE_UTILITY_NATURAL_GAS for li in lines)


def _bill_looks_water(bill: Bill, lines: Sequence[BillLineItem]) -> bool:
    sk = _spend_kind_lower(bill)
    if "water" in sk and "sewer" not in sk:
        return True
    return any(li.canonical_service_key == SERVICE_UTILITY_WATER for li in lines)


def _line_label(li: BillLineItem) -> str:
    return li.raw_label.strip().lower()


def _has_kwh_usage(lines: Sequence[BillLineItem]) -> bool:
    for li in lines:
        unit = (li.quantity_unit or "").strip().lower()
        label = _line_label(li)
        if unit == UNIT_KWH or _KWH_RE.search(label):
            if li.canonical_line_kind in (LINE_KIND_USAGE, LINE_KIND_CHARGE) or li.quantity is not None:
                return True
    return False


def _has_demand_style_line(lines: Sequence[BillLineItem]) -> bool:
    for li in lines:
        label = _line_label(li)
        if _DEMAND_LABEL_RE.search(label) or _KW_NOT_KWH_RE.search(label):
            if li.canonical_line_kind in (LINE_KIND_CHARGE, LINE_KIND_FEE, LINE_KIND_USAGE):
                return True
    return False


def _check_electric_demand_without_usage(bill: Bill, lines: Sequence[BillLineItem]) -> ComparisonFindingResponse | None:
    if bill.spend_domain != SPEND_DOMAIN_UTILITY:
        return None
    if not _bill_looks_electric(bill, lines):
        return None
    if not _has_demand_style_line(lines):
        return None
    if _has_kwh_usage(lines):
        return None
    return _finding(
        rule_id="utility_electric_demand_without_usage",
        title="Demand charge without kWh usage lines",
        summary=(
            "This bill looks electric and includes demand-style charges, but no kWh usage lines "
            "were normalized. Confirm usage rows were not dropped during extraction."
        ),
        evidence={"spend_kind": bill.spend_kind, "pack": "utility_electric"},
    )


def _has_water_usage_quantity(lines: Sequence[BillLineItem]) -> bool:
    for li in lines:
        unit = (li.quantity_unit or "").strip().lower()
        if unit in _WATER_UNITS and li.quantity is not None:
            return True
        label = _line_label(li)
        if li.canonical_line_kind == LINE_KIND_USAGE and any(u in label for u in ("gallon", "ccf", "cubic")):
            return True
    return False


def _check_water_missing_usage(bill: Bill, lines: Sequence[BillLineItem]) -> ComparisonFindingResponse | None:
    if bill.spend_domain != SPEND_DOMAIN_UTILITY:
        return None
    if not _bill_looks_water(bill, lines):
        return None
    if not lines:
        return None
    if _has_water_usage_quantity(lines):
        return None
    return _finding(
        rule_id="utility_water_missing_usage",
        title="Water bill without metered usage lines",
        summary=(
            "This bill is classified as water utility spend but has no gallon/CCF/liter usage lines. "
            "Flat-rate or bundled sewer charges may explain it—still worth verifying extraction."
        ),
        evidence={"spend_kind": bill.spend_kind, "pack": "utility_water"},
    )


def _has_gas_usage_quantity(lines: Sequence[BillLineItem]) -> bool:
    for li in lines:
        unit = (li.quantity_unit or "").strip().lower()
        if unit in _GAS_UNITS and li.quantity is not None:
            return True
        label = _line_label(li)
        if "therm" in label and li.quantity is not None:
            return True
    return False


def _check_gas_missing_usage(bill: Bill, lines: Sequence[BillLineItem]) -> ComparisonFindingResponse | None:
    if bill.spend_domain != SPEND_DOMAIN_UTILITY:
        return None
    if not _bill_looks_gas(bill, lines):
        return None
    if not lines:
        return None
    if _has_gas_usage_quantity(lines):
        return None
    return _finding(
        rule_id="utility_gas_missing_usage",
        title="Gas bill without therm/CCF usage quantities",
        summary=(
            "This bill looks like natural gas spend but has no therm/CCF quantity lines. "
            "Verify usage rows were extracted if the PDF shows metered consumption."
        ),
        evidence={"spend_kind": bill.spend_kind, "pack": "utility_gas"},
    )


def _positive_charge_total(lines: Sequence[BillLineItem]) -> Decimal:
    total = Decimal("0")
    for li in lines:
        if li.amount is not None and li.amount > 0:
            total += li.amount
    return total


def _check_telecom_high_recurring_fees(bill: Bill, lines: Sequence[BillLineItem]) -> ComparisonFindingResponse | None:
    """Telecom: many small fee lines can indicate bundled surcharges worth auditing."""
    if bill.spend_domain != SPEND_DOMAIN_TELECOM:
        return None
    fee_lines = [li for li in lines if li.canonical_line_kind == LINE_KIND_FEE and li.amount and li.amount > 0]
    if len(fee_lines) < 3:
        return None
    fee_sum = sum((li.amount for li in fee_lines if li.amount is not None), Decimal("0"))
    charge_total = _positive_charge_total(lines)
    if charge_total <= 0:
        return None
    pct = (fee_sum / charge_total) * Decimal("100")
    if pct < Decimal("20"):
        return None
    return _finding(
        rule_id="telecom_many_fees",
        title="Several telecom fee lines on one bill",
        summary=(
            f"{len(fee_lines)} fee lines total {fee_sum} {bill.currency} "
            f"({pct.quantize(Decimal('0.1'))}% of positive charges). "
            "Review equipment, regulatory, and one-time surcharges."
        ),
        evidence={"fee_line_count": len(fee_lines), "fee_sum": str(fee_sum), "fee_percent": float(pct)},
    )


def evaluate_domain_packs(bill: Bill) -> list[ComparisonFindingResponse]:
    """Run domain-specific single-bill heuristics for utility and telecom bills."""
    lines = list(bill.line_items)
    findings: list[ComparisonFindingResponse] = []
    for check in (
        lambda: _check_electric_demand_without_usage(bill, lines),
        lambda: _check_water_missing_usage(bill, lines),
        lambda: _check_gas_missing_usage(bill, lines),
        lambda: _check_telecom_high_recurring_fees(bill, lines),
    ):
        result = check()
        if result is not None:
            findings.append(result)
    return findings
