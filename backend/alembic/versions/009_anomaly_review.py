"""§5b audit log: append-only review transitions on ``anomalies`` (tenant-scoped)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_anomaly_review"
down_revision: Union[str, None] = "008_anomalies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "anomalies",
        sa.Column(
            "review_status",
            sa.String(length=32),
            nullable=False,
            server_default="open",
        ),
    )
    op.create_check_constraint(
        "ck_anomalies_review_status",
        "anomalies",
        "review_status IN ('open', 'approved', 'dismissed', 'flagged')",
    )
    op.create_index("ix_anomalies_review_status", "anomalies", ["review_status"], unique=False)
    op.create_index(
        "ix_anomalies_org_review_status",
        "anomalies",
        ["organization_id", "review_status"],
        unique=False,
    )
    op.alter_column("anomalies", "review_status", server_default=None)

    op.create_table(
        "anomaly_review_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("anomaly_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=False),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["anomaly_id"], ["anomalies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "from_status IN ('open', 'approved', 'dismissed', 'flagged')",
            name="ck_anomaly_review_events_from_status",
        ),
        sa.CheckConstraint(
            "to_status IN ('open', 'approved', 'dismissed', 'flagged')",
            name="ck_anomaly_review_events_to_status",
        ),
    )
    op.create_index(
        "ix_anomaly_review_events_anomaly_id",
        "anomaly_review_events",
        ["anomaly_id"],
        unique=False,
    )
    op.create_index(
        "ix_anomaly_review_events_org_id",
        "anomaly_review_events",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_anomaly_review_events_created_at",
        "anomaly_review_events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_anomaly_review_events_created_at", table_name="anomaly_review_events")
    op.drop_index("ix_anomaly_review_events_org_id", table_name="anomaly_review_events")
    op.drop_index("ix_anomaly_review_events_anomaly_id", table_name="anomaly_review_events")
    op.drop_table("anomaly_review_events")
    op.drop_index("ix_anomalies_org_review_status", table_name="anomalies")
    op.drop_index("ix_anomalies_review_status", table_name="anomalies")
    op.drop_constraint("ck_anomalies_review_status", "anomalies", type_="check")
    op.drop_column("anomalies", "review_status")
