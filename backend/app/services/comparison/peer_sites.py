"""Persist and load user-chosen peer sites for §3c on ``bills.summary`` JSONB."""

from __future__ import annotations

import uuid
from typing import Any, Sequence

from app.models.bill import Bill

# Key on ``bills.summary`` — list of site UUID strings the user picked for cross-site compare.
PEER_COMPARISON_SITE_IDS_KEY = "peer_comparison_site_ids"


def read_saved_peer_site_ids(bill: Bill | None) -> list[uuid.UUID]:
    """Return last saved peer site ids from the bill summary (may be empty)."""
    if bill is None or not bill.summary:
        return []
    raw = bill.summary.get(PEER_COMPARISON_SITE_IDS_KEY)
    if not isinstance(raw, list):
        return []
    out: list[uuid.UUID] = []
    for item in raw:
        try:
            out.append(uuid.UUID(str(item)))
        except (ValueError, TypeError):
            continue
    return out


def save_peer_site_ids_to_bill(bill: Bill, site_ids: Sequence[uuid.UUID]) -> None:
    """Merge chosen peer site ids into ``bill.summary`` (does not commit)."""
    merged: dict[str, Any] = dict(bill.summary) if bill.summary else {}
    merged[PEER_COMPARISON_SITE_IDS_KEY] = [str(sid) for sid in site_ids]
    bill.summary = merged


def normalize_user_peer_site_ids(
    anchor: Bill,
    requested: Sequence[uuid.UUID],
) -> list[uuid.UUID]:
    """Drop anchor site and duplicates; preserve caller order."""
    seen: set[uuid.UUID] = set()
    out: list[uuid.UUID] = []
    anchor_site = anchor.site_id
    for sid in requested:
        if anchor_site is not None and sid == anchor_site:
            continue
        if sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out
