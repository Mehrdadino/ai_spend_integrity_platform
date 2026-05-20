"""Labeled golden bills for §3b rule-pack accuracy (no database).

Each case defines a synthetic normalized bill plus expected ``rule_id`` sets.
``run_labeled_accuracy`` scores recall on ``must_include`` and violations on ``must_exclude``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Sequence

from app.constants.normalization import (
    LINE_KIND_CHARGE,
    LINE_KIND_CREDIT,
    LINE_KIND_FEE,
    LINE_KIND_TAX,
    LINE_KIND_USAGE,
    SPEND_DOMAIN_TELECOM,
    SPEND_DOMAIN_UTILITY,
    UNIT_KWH,
)
from app.models.bill import Bill
from app.models.bill_line_item import BillLineItem
from app.services.comparison.rule_pack_v1 import evaluate_rule_pack_v1
from app.services.normalization.service_keys import SERVICE_UTILITY_ELECTRIC


@dataclass(frozen=True)
class LabeledComparisonCase:
    """One synthetic bill scenario with expected rule outcomes."""

    case_id: str
    current: Bill
    priors: tuple[Bill, ...] = ()
    must_include: frozenset[str] = frozenset()
    must_exclude: frozenset[str] = frozenset()


@dataclass
class LabeledAccuracyReport:
    """Aggregate metrics over all labeled cases."""

    case_count: int
    recall_hits: int
    recall_total: int
    exclude_violations: int
    failed_cases: list[str]

    @property
    def recall(self) -> float:
        if self.recall_total == 0:
            return 1.0
        return self.recall_hits / self.recall_total

    @property
    def passed(self) -> bool:
        return not self.failed_cases


def _bill(
    *,
    bill_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
    total: str | None = None,
    spend_domain: str = "utility",
    spend_kind: str | None = "electricity",
    period_end: date | None = date(2026, 3, 31),
    period_start: date | None = None,
    summary: dict | None = None,
    line_items: list[BillLineItem] | None = None,
) -> Bill:
    bid = bill_id or uuid.uuid4()
    b = Bill(
        id=bid,
        organization_id=uuid.uuid4(),
        site_id=site_id if site_id is not None else uuid.uuid4(),
        document_id=uuid.uuid4(),
        spend_domain=spend_domain,
        spend_kind=spend_kind,
        currency="USD",
        normalization_version="norm-v1",
        period_start=period_start,
        period_end=period_end,
        created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        total_amount=Decimal(total) if total is not None else None,
        summary=summary,
    )
    if line_items is not None:
        for li in line_items:
            li.bill_id = bid
        b.line_items = line_items
    else:
        b.line_items = []
    return b


def _line(
    *,
    kind: str,
    label: str,
    amount: str | None = None,
    position: int = 1,
    quantity_unit: str | None = None,
    quantity: str | None = None,
    service_key: str | None = None,
) -> BillLineItem:
    return BillLineItem(
        id=uuid.uuid4(),
        bill_id=uuid.uuid4(),
        position=position,
        raw_label=label,
        canonical_line_kind=kind,
        canonical_service_key=service_key,
        amount=Decimal(amount) if amount is not None else None,
        quantity=Decimal(quantity) if quantity is not None else None,
        quantity_unit=quantity_unit,
        currency="USD",
    )


def build_labeled_cases() -> list[LabeledComparisonCase]:
    """Curated set for pilot regression; extend as real PDFs are labeled."""
    site = uuid.uuid4()
    prior = _bill(site_id=site, total="100.00", period_end=date(2026, 2, 28))

    return [
        LabeledComparisonCase(
            case_id="mom_15pct_increase",
            current=_bill(site_id=site, total="115.00"),
            priors=(prior,),
            must_include=frozenset({"mom_total_change"}),
            must_exclude=frozenset({"no_prior_bill"}),
        ),
        LabeledComparisonCase(
            case_id="mom_small_change_silent",
            current=_bill(site_id=site, total="102.00"),
            priors=(prior,),
            must_include=frozenset(),
            must_exclude=frozenset({"mom_total_change", "no_prior_bill"}),
        ),
        LabeledComparisonCase(
            case_id="tax_high_share",
            current=_bill(
                total="100.00",
                line_items=[
                    _line(kind=LINE_KIND_CHARGE, label="Energy", amount="70.00", position=1),
                    _line(kind=LINE_KIND_TAX, label="City tax", amount="12.00", position=2),
                ],
            ),
            must_include=frozenset({"tax_high_share_of_total"}),
        ),
        LabeledComparisonCase(
            case_id="fees_high_share",
            current=_bill(
                total="100.00",
                line_items=[
                    _line(kind=LINE_KIND_CHARGE, label="Usage", amount="70.00", position=1),
                    _line(kind=LINE_KIND_FEE, label="Rider", amount="20.00", position=2),
                ],
            ),
            must_include=frozenset({"fees_high_share_of_total"}),
            must_exclude=frozenset({"tax_high_share_of_total"}),
        ),
        LabeledComparisonCase(
            case_id="extraction_fallback",
            current=_bill(
                total="50.00",
                summary={
                    "structured_via": "deterministic_fallback",
                    "structured_error": "timeout",
                    "line_count": 1,
                },
                line_items=[_line(kind=LINE_KIND_CHARGE, label="Sample", amount="50.00")],
            ),
            must_include=frozenset({"extraction_structured_fallback"}),
        ),
        LabeledComparisonCase(
            case_id="extraction_low_text",
            current=_bill(
                summary={
                    "text_extraction_method": "pdf_embedded",
                    "text_needs_ocr": True,
                    "text_has_usable_text": False,
                    "text_char_count": 12,
                    "line_count": 1,
                },
                line_items=[_line(kind=LINE_KIND_CHARGE, label="A", amount="10.00")],
            ),
            must_include=frozenset({"extraction_low_text_quality"}),
        ),
        LabeledComparisonCase(
            case_id="extraction_no_lines",
            current=_bill(
                summary={"line_count": 0, "source_extraction_version": "generic-bill-v1"},
                line_items=[],
            ),
            must_include=frozenset({"extraction_no_line_items"}),
        ),
        LabeledComparisonCase(
            case_id="electric_demand_no_kwh",
            current=_bill(
                spend_kind="electricity",
                line_items=[
                    _line(
                        kind=LINE_KIND_CHARGE,
                        label="Demand charge 50 kW",
                        amount="80.00",
                        position=1,
                        service_key=SERVICE_UTILITY_ELECTRIC,
                    ),
                ],
            ),
            must_include=frozenset({"utility_electric_demand_without_usage"}),
        ),
        LabeledComparisonCase(
            case_id="electric_demand_with_kwh_ok",
            current=_bill(
                spend_kind="electricity",
                line_items=[
                    _line(
                        kind=LINE_KIND_USAGE,
                        label="Energy 900 kWh",
                        amount="60.00",
                        position=1,
                        quantity_unit=UNIT_KWH,
                        quantity="900",
                        service_key=SERVICE_UTILITY_ELECTRIC,
                    ),
                    _line(
                        kind=LINE_KIND_CHARGE,
                        label="Demand 40 kW",
                        amount="30.00",
                        position=2,
                        service_key=SERVICE_UTILITY_ELECTRIC,
                    ),
                ],
            ),
            must_exclude=frozenset({"utility_electric_demand_without_usage"}),
        ),
        LabeledComparisonCase(
            case_id="water_missing_usage",
            current=_bill(
                spend_kind="water",
                line_items=[_line(kind=LINE_KIND_CHARGE, label="Water service", amount="45.00")],
            ),
            must_include=frozenset({"utility_water_missing_usage"}),
        ),
        LabeledComparisonCase(
            case_id="gas_missing_usage",
            current=_bill(
                spend_kind="natural_gas",
                line_items=[_line(kind=LINE_KIND_CHARGE, label="Gas service", amount="55.00")],
            ),
            must_include=frozenset({"utility_gas_missing_usage"}),
        ),
        LabeledComparisonCase(
            case_id="telecom_many_fees",
            current=_bill(
                spend_domain=SPEND_DOMAIN_TELECOM,
                spend_kind="broadband",
                total="100.00",
                line_items=[
                    _line(kind=LINE_KIND_CHARGE, label="Internet", amount="60.00", position=1),
                    _line(kind=LINE_KIND_FEE, label="Regulatory", amount="10.00", position=2),
                    _line(kind=LINE_KIND_FEE, label="Equipment", amount="12.00", position=3),
                    _line(kind=LINE_KIND_FEE, label="Franchise", amount="8.00", position=4),
                ],
            ),
            must_include=frozenset({"telecom_many_fees"}),
        ),
        LabeledComparisonCase(
            case_id="first_bill_no_mom",
            current=_bill(),
            priors=(),
            must_include=frozenset({"no_prior_bill"}),
            must_exclude=frozenset({"mom_total_change", "new_fee_lines"}),
        ),
        LabeledComparisonCase(
            case_id="duplicate_lines",
            current=_bill(
                total="100.00",
                line_items=[
                    _line(kind=LINE_KIND_CHARGE, label="Energy", amount="50.00", position=1),
                    _line(kind=LINE_KIND_CHARGE, label="Energy", amount="50.00", position=2),
                ],
            ),
            must_include=frozenset({"duplicate_line_fingerprint"}),
        ),
        LabeledComparisonCase(
            case_id="penalty_fee_label",
            current=_bill(
                line_items=[
                    _line(kind=LINE_KIND_CHARGE, label="Usage", amount="90.00", position=1),
                    _line(kind=LINE_KIND_FEE, label="Late payment fee", amount="10.00", position=2),
                ],
            ),
            must_include=frozenset({"penalty_style_fees"}),
        ),
    ]


def run_labeled_accuracy(cases: Sequence[LabeledComparisonCase] | None = None) -> LabeledAccuracyReport:
    """Evaluate rule pack against labeled expectations; return aggregate report."""
    items = list(cases) if cases is not None else build_labeled_cases()
    recall_hits = 0
    recall_total = 0
    exclude_violations = 0
    failed: list[str] = []

    for case in items:
        findings, _ = evaluate_rule_pack_v1(current=case.current, priors=list(case.priors))
        found = {f.rule_id for f in findings}
        missing = case.must_include - found
        extra = case.must_exclude & found
        recall_total += len(case.must_include)
        recall_hits += len(case.must_include & found)
        exclude_violations += len(extra)
        if missing or extra:
            parts: list[str] = [case.case_id]
            if missing:
                parts.append(f"missing={sorted(missing)}")
            if extra:
                parts.append(f"unexpected={sorted(extra)}")
            failed.append("; ".join(parts))

    return LabeledAccuracyReport(
        case_count=len(items),
        recall_hits=recall_hits,
        recall_total=recall_total,
        exclude_violations=exclude_violations,
        failed_cases=failed,
    )
