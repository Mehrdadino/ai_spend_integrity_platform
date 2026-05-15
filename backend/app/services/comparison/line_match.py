"""Line matching keys for §3b cross-bill comparison (same site, period-over-period).

Fingerprints are deterministic strings from ``canonical_line_kind`` plus a normalized
service key or label so "City tax" on one bill matches "city tax" on the next.
"""

from __future__ import annotations

import re

from app.models.bill_line_item import BillLineItem

_WS_RE = re.compile(r"\s+")


def normalize_match_label(raw: str) -> str:
    """Lowercase, collapse whitespace, strip common punctuation for stable matching."""
    t = raw.strip().lower()
    t = _WS_RE.sub(" ", t)
    return t.strip(" .,;:-_")


def line_fingerprint(line: BillLineItem) -> str:
    """Stable key for ``canonical_line_kind`` + service/label within one site history."""
    label_key = line.canonical_service_key or normalize_match_label(line.raw_label)
    return f"{line.canonical_line_kind}|{label_key}"


def fee_line_fingerprints(lines: list[BillLineItem]) -> set[str]:
    """Fingerprints of fee-kind lines only (used by ``new_fee_lines`` rule)."""
    from app.constants.normalization import LINE_KIND_FEE

    return {line_fingerprint(li) for li in lines if li.canonical_line_kind == LINE_KIND_FEE}
