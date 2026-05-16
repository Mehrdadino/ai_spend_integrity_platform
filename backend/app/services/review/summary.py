"""Roll up §5 review fields for list APIs (documents + anomalies inbox)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Optional

# Highest value wins when a document has multiple anomaly rows (attention-first).
_REVIEW_STATUS_PRIORITY: dict[str, int] = {
    "flagged": 4,
    "open": 3,
    "dismissed": 2,
    "approved": 1,
}


def aggregate_review_status_for_document(statuses: Iterable[str]) -> Optional[str]:
    """Pick one inbox status for a document from its anomaly ``review_status`` values.

    Returns ``None`` when the document has no anomalies. Unknown statuses are ignored.
    """
    best: Optional[str] = None
    best_rank = 0
    for raw in statuses:
        s = raw.strip().lower()
        rank = _REVIEW_STATUS_PRIORITY.get(s, 0)
        if rank > best_rank:
            best_rank = rank
            best = s
    return best
