"""Persist §3 comparison findings per bill (``anomalies`` table).

One bill can have zero or many anomalies for a given ``rule_pack_version``; rerunning
comparison replaces that snapshot (delete + insert) so persisted state matches §3b.

Revision ID: 008_anomalies
Revises: 007_documents_deleted_at
Create Date: 2026-05-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_anomalies"
down_revision: Union[str, None] = "007_documents_deleted_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "anomalies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("bill_line_item_id", sa.Uuid(), nullable=True),
        sa.Column("compared_to_bill_id", sa.Uuid(), nullable=True),
        sa.Column("rule_pack_version", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.String(length=64), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("fingerprint", sa.String(length=512), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bill_line_item_id"], ["bill_line_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["compared_to_bill_id"], ["bills.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_anomalies_organization_id", "anomalies", ["organization_id"], unique=False)
    op.create_index("ix_anomalies_site_id", "anomalies", ["site_id"], unique=False)
    op.create_index("ix_anomalies_document_id", "anomalies", ["document_id"], unique=False)
    op.create_index("ix_anomalies_bill_id", "anomalies", ["bill_id"], unique=False)
    op.create_index("ix_anomalies_period_end", "anomalies", ["period_end"], unique=False)
    op.create_index("ix_anomalies_created_at", "anomalies", ["created_at"], unique=False)
    # Dedupe keyed rows when a site exists (PostgreSQL UNIQUE treats NULL ``site_id`` as distinct).
    op.create_index(
        "uq_anomalies_site_org_rule_period_fp",
        "anomalies",
        ["organization_id", "site_id", "rule_id", "period_end", "fingerprint"],
        unique=True,
        postgresql_where=sa.text("site_id IS NOT NULL"),
    )
    op.create_index(
        "uq_anomalies_nosite_org_doc_rule_fp",
        "anomalies",
        ["organization_id", "document_id", "rule_id", "fingerprint"],
        unique=True,
        postgresql_where=sa.text("site_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_anomalies_nosite_org_doc_rule_fp", table_name="anomalies")
    op.drop_index("uq_anomalies_site_org_rule_period_fp", table_name="anomalies")
    op.drop_index("ix_anomalies_created_at", table_name="anomalies")
    op.drop_index("ix_anomalies_period_end", table_name="anomalies")
    op.drop_index("ix_anomalies_bill_id", table_name="anomalies")
    op.drop_index("ix_anomalies_document_id", table_name="anomalies")
    op.drop_index("ix_anomalies_site_id", table_name="anomalies")
    op.drop_index("ix_anomalies_organization_id", table_name="anomalies")
    op.drop_table("anomalies")
