"""§3c peer rule pack: cross-site fee prevalence and usage/total outlier checks.

Evaluates one **anchor** bill against a gated peer set (same org, domain, service slice,
billing-month window). Does not replace §3b same-site MoM rules.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from statistics import median
from typing import Any, Sequence
from uuid import UUID

from app.models.bill import Bill
from app.schemas.comparison import ComparisonFindingResponse, ComparisonSeverity
from app.services.comparison.formatting import format_percent
from app.services.comparison.line_match import fee_line_fingerprints, line_fingerprint
from app.services.comparison.peer_config import (
    MAX_PEER_BILLS,
    MIN_PEER_SITES,
    PEER_FEE_RARE_MAX_PEER_MATCHES,
    PEER_FEE_WIDESPREAD_PCT,
    PEER_OUTLIER_MEDIAN_FACTOR,
    PEER_OUTLIER_P75_FACTOR,
    PEER_RULE_PACK_VERSION,
)
from app.services.comparison.peer_metrics import PeerBillMetrics, extract_peer_metrics
from app.services.comparison.peer_slice import (
    bills_match_peer_slice,
    peer_domain_supported,
    peer_service_slice_key,
    period_window_for_anchor,
)
from app.services.comparison.period import bill_period_sort_key, effective_period_end


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


def _newest_bill_per_site(bills: Sequence[Bill]) -> list[Bill]:
    """Keep the newest bill per ``site_id`` within an already-filtered candidate list."""
    by_site: dict[UUID, Bill] = {}
    for bill in bills:
        if bill.site_id is None:
            continue
        prior = by_site.get(bill.site_id)
        if prior is None or bill_period_sort_key(bill) > bill_period_sort_key(prior):
            by_site[bill.site_id] = bill
    return list(by_site.values())


def resolve_peer_set(
    anchor: Bill,
    candidates: Sequence[Bill],
) -> list[Bill]:
    """Filter SQL candidates to matching slice and cap at ``MAX_PEER_BILLS`` (newest per site)."""
    matched = [b for b in candidates if bills_match_peer_slice(anchor, b)]
    per_site = _newest_bill_per_site(matched)
    per_site.sort(key=bill_period_sort_key, reverse=True)
    return per_site[:MAX_PEER_BILLS]


def _percentile_75(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    ordered = sorted(values)
    n = len(ordered)
    if n == 1:
        return ordered[0]
    rank = 0.75 * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = Decimal(str(rank - lo))
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def _median_decimal(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return Decimal(str(median([float(v) for v in values])))


def _period_window_evidence(anchor: Bill) -> dict[str, Any]:
    month_start, month_end, window_start, window_end = period_window_for_anchor(anchor)
    return {
        "period_window": {
            "month_start": month_start.isoformat(),
            "month_end": month_end.isoformat(),
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
        },
        "service_slice": peer_service_slice_key(anchor),
        "spend_domain": anchor.spend_domain,
    }


def _check_insufficient_peers(
    anchor: Bill,
    peers: Sequence[Bill],
    *,
    min_peer_sites: int,
) -> ComparisonFindingResponse | None:
    site_ids = {b.site_id for b in peers if b.site_id is not None}
    if len(site_ids) >= min_peer_sites:
        return None
    ev = _period_window_evidence(anchor)
    ev["peer_site_count"] = len(site_ids)
    ev["min_peer_sites"] = min_peer_sites
    return _finding(
        rule_id="not_comparable_insufficient_peers",
        severity="info",
        title="Not enough peer sites for cross-site comparison",
        summary=(
            f"Found bills from {len(site_ids)} other site(s) in the same service slice and "
            f"billing window; need at least {min_peer_sites} for peer benchmarks."
        ),
        evidence=ev,
    )


def _check_wrong_domain(anchor: Bill) -> ComparisonFindingResponse | None:
    if peer_domain_supported(anchor):
        return None
    return _finding(
        rule_id="not_comparable_wrong_domain",
        severity="info",
        title="Cross-site comparison not available for this spend domain",
        summary=(
            f"Peer benchmarking in v1 supports utility and telecom bills; "
            f"this bill is tagged ``{anchor.spend_domain}``."
        ),
        evidence={"spend_domain": anchor.spend_domain},
    )


def _fee_line_display_name(anchor: Bill, fingerprint: str) -> str:
    """Human label for peer fee copy (prefer anchor ``raw_label`` over internal fingerprint)."""
    for li in anchor.line_items:
        if line_fingerprint(li) == fingerprint:
            label = (li.raw_label or "").strip()
            if label:
                return label
    if "|" in fingerprint:
        return fingerprint.split("|", 1)[1]
    return fingerprint


def _fee_rules(
    anchor: Bill,
    peers: Sequence[Bill],
    *,
    min_peers_for_rules: int = 2,
) -> list[ComparisonFindingResponse]:
    """``peer_fee_line_rare`` and ``peer_fee_line_widespread`` over fee fingerprints."""
    findings: list[ComparisonFindingResponse] = []
    anchor_fees = fee_line_fingerprints(anchor.line_items)
    if not anchor_fees:
        return findings

    peer_count = len(peers)
    if peer_count < min_peers_for_rules:
        return findings

    peer_site_ids: list[str] = []
    for peer in peers:
        if peer.site_id is not None:
            peer_site_ids.append(str(peer.site_id))

    for fp in sorted(anchor_fees):
        peers_with_fee = 0
        sites_with_fee: list[str] = []
        for peer in peers:
            if fp in fee_line_fingerprints(peer.line_items):
                peers_with_fee += 1
                if peer.site_id is not None:
                    sites_with_fee.append(str(peer.site_id))

        fee_label = _fee_line_display_name(anchor, fp)
        base_ev = {
            **_period_window_evidence(anchor),
            "fingerprint": fp,
            "fee_label": fee_label,
            "peer_count": peer_count,
            "peers_with_fee": peers_with_fee,
            "peer_site_ids": sites_with_fee,
        }

        if peers_with_fee <= PEER_FEE_RARE_MAX_PEER_MATCHES:
            findings.append(
                _finding(
                    rule_id="peer_fee_line_rare",
                    severity="warning",
                    title="Fee line rare vs peer sites",
                    summary=(
                        f"Fee line “{fee_label}” appears on this bill but on only {peers_with_fee} of "
                        f"{peer_count} peer account(s) in the same billing window."
                    ),
                    evidence=base_ev,
                )
            )
            continue

        prevalence = (Decimal(peers_with_fee) / Decimal(peer_count)) * Decimal("100")
        if prevalence >= PEER_FEE_WIDESPREAD_PCT:
            ev = dict(base_ev)
            ev["prevalence_pct"] = float(prevalence)
            findings.append(
                _finding(
                    rule_id="peer_fee_line_widespread",
                    severity="info",
                    title="Fee line common across peer sites",
                    summary=(
                        f"Fee line “{fee_label}” appears on this bill and on {peers_with_fee} of "
                        f"{peer_count} peer accounts ({format_percent(prevalence)}%) — "
                        "likely a portfolio-wide charge."
                    ),
                    evidence=ev,
                )
            )

    return findings


def _check_mixed_units(
    anchor: Bill,
    peers: Sequence[Bill],
) -> ComparisonFindingResponse | None:
    anchor_m = extract_peer_metrics(anchor)
    if not anchor_m.has_kwh_usage:
        return None
    peers_with_kwh = sum(1 for p in peers if extract_peer_metrics(p).has_kwh_usage)
    if peers_with_kwh >= max(1, len(peers) // 2):
        return None
    ev = _period_window_evidence(anchor)
    ev["peers_with_kwh"] = peers_with_kwh
    ev["peer_count"] = len(peers)
    return _finding(
        rule_id="not_comparable_mixed_units",
        severity="info",
        title="Peer bills lack comparable usage units",
        summary=(
            "This bill has kWh-style usage lines but too few peer bills report the same unit; "
            "skipping usage outlier math."
        ),
        evidence=ev,
    )


def _outlier_for_metric(
    *,
    anchor: Bill,
    peers: Sequence[Bill],
    metric_name: str,
    anchor_value: Decimal,
    peer_values: list[Decimal],
    unit: str,
) -> ComparisonFindingResponse | None:
    if len(peer_values) < MIN_PEER_SITES:
        return None
    med = _median_decimal(peer_values)
    p75 = _percentile_75(peer_values)
    if med <= 0 and p75 <= 0:
        return None
    high_vs_p75 = anchor_value > p75 * PEER_OUTLIER_P75_FACTOR
    high_vs_median = med > 0 and anchor_value > med * PEER_OUTLIER_MEDIAN_FACTOR
    if not high_vs_p75 and not high_vs_median:
        return None
    ev = {
        **_period_window_evidence(anchor),
        "metric": metric_name,
        "anchor_value": float(anchor_value),
        "peer_median": float(med),
        "peer_p75": float(p75),
        "peer_count": len(peer_values),
        "unit": unit,
        "trigger": "p75_x1.25" if high_vs_p75 else "median_x2",
    }
    ratio = float(anchor_value / med) if med > 0 else None
    ratio_part = f" ({ratio:.1f}× peer median)" if ratio is not None else ""
    return _finding(
        rule_id="peer_usage_or_total_outlier",
        severity="warning",
        title="High vs peer sites",
        summary=(
            f"{metric_name} at this site ({anchor_value} {unit}) is elevated vs "
            f"{len(peer_values)} peer account(s){ratio_part}."
        ),
        evidence=ev,
    )


def _usage_outlier_rules(
    anchor: Bill,
    peers: Sequence[Bill],
) -> list[ComparisonFindingResponse]:
    findings: list[ComparisonFindingResponse] = []
    anchor_m = extract_peer_metrics(anchor)

    peer_totals = [p.total_amount for p in peers if p.total_amount is not None]
    if anchor_m.bill_total is not None and len(peer_totals) >= MIN_PEER_SITES:
        f = _outlier_for_metric(
            anchor=anchor,
            peers=peers,
            metric_name="bill_total",
            anchor_value=anchor_m.bill_total,
            peer_values=peer_totals,
            unit=anchor.currency,
        )
        if f is not None:
            findings.append(f)

    if anchor_m.has_kwh_usage and anchor_m.total_kwh is not None:
        peer_kwh = [
            extract_peer_metrics(p).total_kwh
            for p in peers
            if extract_peer_metrics(p).total_kwh is not None
        ]
        if len(peer_kwh) >= MIN_PEER_SITES:
            f = _outlier_for_metric(
                anchor=anchor,
                peers=peers,
                metric_name="total_kwh",
                anchor_value=anchor_m.total_kwh,
                peer_values=peer_kwh,
                unit="kWh",
            )
            if f is not None:
                findings.append(f)

        if anchor_m.cost_per_kwh is not None:
            peer_cpp = [
                extract_peer_metrics(p).cost_per_kwh
                for p in peers
                if extract_peer_metrics(p).cost_per_kwh is not None
            ]
            if len(peer_cpp) >= MIN_PEER_SITES:
                f = _outlier_for_metric(
                    anchor=anchor,
                    peers=peers,
                    metric_name="cost_per_kwh",
                    anchor_value=anchor_m.cost_per_kwh,
                    peer_values=peer_cpp,
                    unit=f"{anchor.currency}/kWh",
                )
                if f is not None:
                    findings.append(f)

    return findings


def evaluate_peer_pack_v1(
    *,
    anchor: Bill,
    peer_candidates: Sequence[Bill],
    min_peer_sites: int | None = None,
    user_selected_peer_site_ids: Sequence[UUID] | None = None,
) -> list[ComparisonFindingResponse]:
    """Run §3c rules; always returns explicit comparability info findings when gated out.

    When ``user_selected_peer_site_ids`` is set, ``min_peer_sites`` defaults to 1 (user picked
    comparables). Otherwise the production default ``MIN_PEER_SITES`` applies.
    """
    threshold = MIN_PEER_SITES
    if user_selected_peer_site_ids:
        threshold = 1
    if min_peer_sites is not None:
        threshold = min_peer_sites

    findings: list[ComparisonFindingResponse] = []

    if anchor.site_id is None:
        findings.append(
            _finding(
                rule_id="not_comparable_no_site",
                severity="info",
                title="Assign a site for cross-site comparison",
                summary="Peer benchmarks need a site on the anchor bill.",
            )
        )
        return findings

    wrong = _check_wrong_domain(anchor)
    if wrong is not None:
        findings.append(wrong)
        return findings

    peers = resolve_peer_set(anchor, peer_candidates)
    insufficient = _check_insufficient_peers(anchor, peers, min_peer_sites=threshold)
    if insufficient is not None:
        if user_selected_peer_site_ids:
            insufficient.evidence["user_peer_site_ids"] = [str(s) for s in user_selected_peer_site_ids]
        findings.append(insufficient)
        return findings

    mixed = _check_mixed_units(anchor, peers)
    if mixed is not None:
        findings.append(mixed)
        return findings

    fee_min = 1 if user_selected_peer_site_ids else 2
    findings.extend(_fee_rules(anchor, peers, min_peers_for_rules=fee_min))
    findings.extend(_usage_outlier_rules(anchor, peers))

    if not any(f.rule_id.startswith("peer_") for f in findings):
        ev = _period_window_evidence(anchor)
        ev["peer_count"] = len(peers)
        findings.append(
            _finding(
                rule_id="peer_comparable_no_signals",
                severity="info",
                title="Peer comparison completed",
                summary=(
                    f"Compared to {len(peers)} peer bill(s) from other sites; "
                    "no cross-site fee or usage outliers detected."
                ),
                evidence=ev,
            )
        )

    return findings


def peer_rule_pack_version() -> str:
    """Expose version constant for callers (evaluate / materialize)."""
    return PEER_RULE_PACK_VERSION
