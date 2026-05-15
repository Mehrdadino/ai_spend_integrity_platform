"""Historical comparison helpers (§3): period ordering and prior-bill selection (3a).

Rule packs (**3b**) and anomaly persistence (**3d**) build on these primitives.
"""

from app.services.comparison.period import (
    BILL_ORDERING_NOTE,
    bill_period_sort_key,
    effective_period_end,
    select_prior_bills,
)

__all__ = [
    "BILL_ORDERING_NOTE",
    "bill_period_sort_key",
    "effective_period_end",
    "select_prior_bills",
]
