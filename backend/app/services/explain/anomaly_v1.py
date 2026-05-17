"""§4b/§4c: template explanations + confidence tiers from ``anomalies.evidence`` JSONB (no LLM).

**4a** is satisfied by the evidence already written at compare time; this module only renders
human-facing copy from those fields so the inbox stays stable across API deploys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

# Bumped when templates or confidence rules change materially (LLM polish would use a new suffix).
EXPLAIN_TEMPLATE_VERSION = "explain-v1"

ConfidenceLevel = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class ExplainabilityV1:
    """§4 read-side bundle attached to list/detail anomaly responses."""

    explanation: str
    confidence: ConfidenceLevel
    reasons: tuple[str, ...]
    version: str = EXPLAIN_TEMPLATE_VERSION


def build_explainability_v1(
    *,
    rule_id: str,
    severity: str,
    evidence: Mapping[str, Any],
    summary: str,
) -> ExplainabilityV1:
    """Return grounded narrative + heuristic confidence for one persisted anomaly row."""
    ev = dict(evidence) if evidence else {}
    if rule_id == "mom_total_change":
        return _mom_total(ev, severity=severity)
    if rule_id == "header_total_mismatch":
        return _header_mismatch(ev)
    if rule_id == "new_fee_line":
        return _new_fee_line(ev)
    if rule_id == "new_fee_lines":
        return _new_fee_lines_aggregate(ev, summary=summary)
    if rule_id == "no_site_assigned":
        return _no_site(summary=summary)
    if rule_id == "no_prior_bill":
        return _no_prior(summary=summary)
    if rule_id == "duplicate_line_fingerprint":
        return _duplicate_lines(ev)
    if rule_id == "fees_high_share_of_total":
        return _fees_high_share(ev)
    if rule_id == "penalty_style_fees":
        return _penalty_fees(ev)
    if rule_id == "missing_period_dates":
        return _missing_period(summary=summary)
    if rule_id == "credits_exceed_charges":
        return _credits_exceed(ev)
    return ExplainabilityV1(
        explanation=(
            f"This signal uses rule “{rule_id}”. The pipeline stored a short summary; "
            "extend explain templates when this rule becomes common. "
            f"Summary: {summary}"
        ),
        confidence="medium",
        reasons=("No dedicated §4 template for this rule yet.",),
        version=EXPLAIN_TEMPLATE_VERSION,
    )


def _tier_for_keys(required: Sequence[str], ev: Mapping[str, Any]) -> tuple[ConfidenceLevel, tuple[str, ...]]:
    """Higher confidence when every required evidence key is present and non-empty."""
    missing = [k for k in required if not _non_empty_scalar(ev.get(k))]
    if not missing:
        return "high", ("All expected metric fields are present in stored evidence.",)
    if len(missing) == 1:
        return "medium", (f"Missing or empty field: {missing[0]}; narrative may be incomplete.",)
    return "low", (f"Several fields missing ({', '.join(missing)}); using fallbacks where possible.",)


def _non_empty_scalar(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, list):
        return bool(value)
    return True


def _get_str(ev: Mapping[str, Any], key: str, default: str = "—") -> str:
    raw = ev.get(key)
    if raw is None:
        return default
    s = str(raw).strip()
    return s if s else default


def _mom_total(ev: Mapping[str, Any], *, severity: str) -> ExplainabilityV1:
    cur = _get_str(ev, "current_total")
    prior = _get_str(ev, "prior_total")
    delta = _get_str(ev, "delta_amount")
    cur_code = _get_str(ev, "currency")
    pct_raw = ev.get("delta_percent")
    tier, reasons = _tier_for_keys(("current_total", "prior_total", "delta_amount"), ev)
    pct_note = ""
    if pct_raw is not None and _non_empty_scalar(pct_raw):
        pct_note = f" That is about {pct_raw}% of the prior bill total."
    explanation = (
        f"We compared this bill’s header total ({cur} {cur_code}) to the immediate prior bill "
        f"at the same site ({prior} {cur_code}). The difference is {delta} {cur_code}.{pct_note} "
        f"The rule marked this as “{severity}” using fixed month-over-month thresholds."
    )
    return ExplainabilityV1(explanation=explanation, confidence=tier, reasons=reasons)


def _header_mismatch(ev: Mapping[str, Any]) -> ExplainabilityV1:
    header = _get_str(ev, "header_total")
    lines_sum = _get_str(ev, "lines_sum")
    diff = _get_str(ev, "difference")
    cur_code = _get_str(ev, "currency")
    tier, reasons = _tier_for_keys(("header_total", "lines_sum", "difference"), ev)
    explanation = (
        f"The bill’s stated total ({header} {cur_code}) does not match the sum of normalized line amounts "
        f"({lines_sum} {cur_code}) on this document. The gap is {diff} {cur_code}. "
        "This usually means extraction dropped a line, double-counted a credit, or the PDF header "
        "reflects taxes/charges we have not yet mapped to lines."
    )
    return ExplainabilityV1(explanation=explanation, confidence=tier, reasons=reasons)


def _new_fee_line(ev: Mapping[str, Any]) -> ExplainabilityV1:
    line = ev.get("line")
    tier: ConfidenceLevel = "high"
    reasons: tuple[str, ...] = ("Line-level evidence is present.",)
    if not isinstance(line, dict):
        tier = "low"
        reasons = ("Expected a ``line`` object in evidence for this row.",)
        label, amt, cur = "—", "—", ""
    else:
        label = _get_str(line, "raw_label")
        amt = _get_str(line, "amount")
        cur = _get_str(line, "currency")
        if label == "—" or amt == "—":
            tier = "medium"
            reasons = ("Some line fields are missing in stored evidence.",)

    prior_pe = _get_str(ev, "prior_period_end", default="")
    prior_id = _get_str(ev, "prior_bill_id", default="")

    prior_bits = []
    if prior_pe and prior_pe != "—":
        prior_bits.append(f"the prior bill period ending {prior_pe}")
    if prior_id and prior_id != "—":
        prior_bits.append(f"prior bill id `{prior_id}`")
    prior_phrase = ""
    if prior_bits:
        prior_phrase = " compared to " + " and ".join(prior_bits) + "."

    amt_cur = f"{amt} {cur}".strip() if cur else amt
    explanation = (
        f"A fee labeled “{label}” appears on this bill for {amt_cur}, but no matching fee "
        f"fingerprint was seen on the prior bill for this site.{prior_phrase} "
        "Review whether this charge is recurring, introductory, one-off, or a misclassification."
    )
    return ExplainabilityV1(explanation=explanation, confidence=tier, reasons=reasons)


def _new_fee_lines_aggregate(ev: Mapping[str, Any], *, summary: str) -> ExplainabilityV1:
    """Fallback row when list expansion yields a single aggregate finding."""
    tier, reasons = _tier_for_keys(("count", "prior_bill_id"), ev)
    count = ev.get("count")
    explanation = (
        f"The comparison found {count} new fee line(s) versus the immediate prior bill. {summary}"
    )
    if not isinstance(count, int):
        explanation = summary
        tier = "medium"
        reasons = (*reasons, "Aggregate count missing; using summary only.")
    return ExplainabilityV1(explanation=explanation.strip(), confidence=tier, reasons=reasons)


def _no_site(*, summary: str) -> ExplainabilityV1:
    explanation = (
        "This bill is not tied to a site (facility/location). Without a shared site key, "
        "the platform cannot pick a credible prior bill for month-over-month math. "
        f"{summary}"
    )
    return ExplainabilityV1(
        explanation=explanation.strip(),
        confidence="high",
        reasons=("Operational rule only; evidence is descriptive.",),
    )


def _no_prior(*, summary: str) -> ExplainabilityV1:
    explanation = (
        "There is no older normalized bill for this site yet, so volatility and fee-delta checks "
        f"against a prior period cannot run. {summary}"
    )
    return ExplainabilityV1(
        explanation=explanation.strip(),
        confidence="high",
        reasons=("Operational rule only; evidence is descriptive.",),
    )


def _duplicate_lines(ev: Mapping[str, Any]) -> ExplainabilityV1:
    groups = ev.get("duplicate_groups")
    tier: ConfidenceLevel = "high"
    reasons: tuple[str, ...] = ("Duplicate fingerprint groups are listed in evidence.",)
    if not isinstance(groups, list) or not groups:
        tier = "low"
        reasons = ("Expected duplicate_groups in evidence.",)
        count_note = "Several line items share the same normalized fingerprint."
    else:
        first = groups[0] if isinstance(groups[0], dict) else {}
        label = _get_str(first, "raw_label")
        n = first.get("count", 2)
        count_note = f"“{label}” appears {n} times with the same classification."
    explanation = (
        f"On this bill alone, {count_note} That can indicate duplicate charges on one invoice "
        "rather than a month-over-month change."
    )
    return ExplainabilityV1(explanation=explanation, confidence=tier, reasons=reasons)


def _fees_high_share(ev: Mapping[str, Any]) -> ExplainabilityV1:
    fee_sum = _get_str(ev, "fee_sum")
    total = _get_str(ev, "bill_total")
    pct = ev.get("fee_percent")
    cur = _get_str(ev, "currency")
    tier, reasons = _tier_for_keys(("fee_sum", "bill_total", "fee_percent"), ev)
    pct_note = f" ({pct}% of the bill)" if pct is not None else ""
    explanation = (
        f"Fee lines on this bill add up to {fee_sum} {cur} against a total of {total} {cur}{pct_note}. "
        "High fee share is a common review target even without prior bills to compare."
    )
    return ExplainabilityV1(explanation=explanation, confidence=tier, reasons=reasons)


def _penalty_fees(ev: Mapping[str, Any]) -> ExplainabilityV1:
    count = ev.get("count")
    tier, reasons = _tier_for_keys(("count",), ev)
    explanation = (
        f"We flagged {count} fee line(s) whose labels match penalty/late/reconnect patterns. "
        "These charges are worth disputing or verifying even on a first upload."
    )
    if not isinstance(count, int):
        explanation = (
            "One or more fee lines look like penalties or late charges based on label keywords."
        )
        tier = "medium"
    return ExplainabilityV1(explanation=explanation, confidence=tier, reasons=reasons)


def _missing_period(*, summary: str) -> ExplainabilityV1:
    explanation = (
        "We could not read a service period from this bill. Period dates help order bills and "
        f"pick the right prior month. {summary}"
    )
    return ExplainabilityV1(
        explanation=explanation.strip(),
        confidence="high",
        reasons=("Data-quality signal from extraction metadata.",),
    )


def _credits_exceed(ev: Mapping[str, Any]) -> ExplainabilityV1:
    credits = _get_str(ev, "credit_sum")
    charges = _get_str(ev, "positive_non_credit_sum")
    cur = _get_str(ev, "currency")
    tier, reasons = _tier_for_keys(("credit_sum", "positive_non_credit_sum"), ev)
    explanation = (
        f"Credits on this bill total {credits} {cur} while other positive lines sum to {charges} {cur}. "
        "Confirm this is an adjustment or net-credit invoice rather than a mapping error."
    )
    return ExplainabilityV1(explanation=explanation, confidence=tier, reasons=reasons)
