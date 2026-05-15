"""§5a: valid review transitions + transactional write to ``anomalies`` + §5b audit row."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.anomaly import Anomaly
from app.models.anomaly_review_event import AnomalyReviewEvent

REVIEW_STATUSES = frozenset({"open", "approved", "dismissed", "flagged"})

# Allowed edges for the lightweight MVP inbox (re-open from terminal states; escalate via flagged).
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"approved", "dismissed", "flagged"}),
    "flagged": frozenset({"approved", "dismissed", "open"}),
    "approved": frozenset({"open", "flagged"}),
    "dismissed": frozenset({"open", "flagged"}),
}


class ReviewTransitionError(ValueError):
    """Raised when ``to_status`` is unknown or not allowed from the current state."""


def apply_review_transition(
    session: Session,
    *,
    anomaly: Anomaly,
    to_status: str,
    note: Optional[str] = None,
    actor_user_id: Optional[uuid.UUID] = None,
) -> Anomaly:
    """Mutate ``anomaly.review_status``, append an ``AnomalyReviewEvent``, and ``flush``.

    Caller must have loaded ``anomaly`` scoped to the correct ``organization_id``.
    """
    ts = to_status.strip().lower()
    if ts not in REVIEW_STATUSES:
        raise ReviewTransitionError(f"Invalid review status: {to_status!r}")
    cur = anomaly.review_status
    allowed = ALLOWED_TRANSITIONS.get(cur, frozenset())
    if ts not in allowed:
        raise ReviewTransitionError(f"Cannot move from {cur!r} to {ts!r}")
    if cur == ts:
        raise ReviewTransitionError("Already in this status.")

    anomaly.review_status = ts
    session.add(
        AnomalyReviewEvent(
            organization_id=anomaly.organization_id,
            anomaly_id=anomaly.id,
            from_status=cur,
            to_status=ts,
            note=(note.strip() if note and note.strip() else None),
            actor_user_id=actor_user_id,
        )
    )
    session.flush()
    return anomaly
