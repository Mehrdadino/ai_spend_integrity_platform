"""§3e: composite index for same-site bill history ordered by billing period.

Supports ``list_bills_for_site`` / prior-bill SQL (``organization_id`` + ``site_id`` +
``coalesce(period_end, period_start, created_at::date)`` DESC). Partial index skips rows
with no ``site_id`` (not comparable until assigned).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "010_bills_site_period"
down_revision: Union[str, None] = "009_anomaly_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Expression index matches ``_bill_period_end_expr()`` in ``repositories/bills.py``.
    op.execute(
        """
        CREATE INDEX ix_bills_org_site_period_sort
        ON bills (
            organization_id,
            site_id,
            (COALESCE(period_end, period_start, (created_at AT TIME ZONE 'UTC')::date)) DESC,
            created_at DESC,
            id DESC
        )
        WHERE site_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bills_org_site_period_sort")
