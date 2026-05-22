"""§3c peer comparability: service slice keys and billing-period windows.

Peers are gated by org + ``spend_domain`` + service slice + calendar-month window,
not by invoice address text.
"""

from __future__ import annotations

from calendar import monthrange
from collections import Counter
from datetime import date, timedelta

from app.constants.normalization import SPEND_DOMAIN_TELECOM, SPEND_DOMAIN_UTILITY
from app.models.bill import Bill
from app.services.comparison.period import effective_period_end
from app.services.comparison.peer_config import PERIOD_WINDOW_SLACK_DAYS
from app.services.normalization.service_keys import (
    SERVICE_UTILITY_ELECTRIC,
    SERVICE_UTILITY_NATURAL_GAS,
    SERVICE_UTILITY_WATER,
)


def peer_service_slice_key(bill: Bill) -> str:
    """Stable slice id: ``spend_kind`` plus dominant ``canonical_service_key`` on lines."""
    sk = (bill.spend_kind or "").strip().lower() or "_none"
    keys = [li.canonical_service_key for li in bill.line_items if li.canonical_service_key]
    if keys:
        dominant = Counter(keys).most_common(1)[0][0]
        return f"{sk}|{dominant}"
    # Infer slice from spend_kind when lines lack service keys (common on sparse extracts).
    inferred = _infer_service_from_spend_kind(sk)
    if inferred:
        return f"{sk}|{inferred}"
    return sk


def _infer_service_from_spend_kind(spend_kind_lower: str) -> str | None:
    if "electric" in spend_kind_lower or spend_kind_lower in ("electricity", "power"):
        return SERVICE_UTILITY_ELECTRIC
    if "gas" in spend_kind_lower or "natural" in spend_kind_lower:
        return SERVICE_UTILITY_NATURAL_GAS
    if "water" in spend_kind_lower:
        return SERVICE_UTILITY_WATER
    return None


def period_window_for_anchor(
    anchor: Bill,
    *,
    slack_days: int = PERIOD_WINDOW_SLACK_DAYS,
) -> tuple[date, date, date, date]:
    """Return ``(month_start, month_end, window_start, window_end)`` for peer SQL filters."""
    anchor_end = effective_period_end(anchor)
    month_start = anchor_end.replace(day=1)
    last_day = monthrange(anchor_end.year, anchor_end.month)[1]
    month_end = anchor_end.replace(day=last_day)
    window_start = month_start - timedelta(days=slack_days)
    window_end = month_end + timedelta(days=slack_days)
    return month_start, month_end, window_start, window_end


def peer_domain_supported(bill: Bill) -> bool:
    """True when ``spend_domain`` is in the v1 peer pack allowlist."""
    domain = (bill.spend_domain or "").strip().lower()
    return domain in (SPEND_DOMAIN_UTILITY, SPEND_DOMAIN_TELECOM)


def bills_match_peer_slice(anchor: Bill, candidate: Bill) -> bool:
    """Same ``spend_domain`` and service slice as anchor."""
    if (candidate.spend_domain or "").strip().lower() != (anchor.spend_domain or "").strip().lower():
        return False
    return peer_service_slice_key(candidate) == peer_service_slice_key(anchor)
