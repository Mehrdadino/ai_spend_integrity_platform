"""Historical comparison (§3): prior-bill queries (3a), rule pack evaluation (3b), §3d persistence.

Import ``evaluate_document_comparison`` from ``app.services.comparison.evaluate`` rather than this
package to avoid a circular import with ``app.repositories.bills``.
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
