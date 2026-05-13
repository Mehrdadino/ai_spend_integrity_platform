"""Add ``bills`` and ``bill_line_items`` for normalized spend (pillars 2c–2d).

One ``bill`` per ``document_id`` (idempotent worker re-runs replace the row).
``spend_domain`` / ``spend_kind`` are open-ended strings with app-level vocabularies
so we can add water, telecom, contracts, etc. without new migrations for each domain.

Revision ID: 006_bills_lines
Revises: 005_drop_ingest_token
Create Date: 2026-05-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_bills_lines"
down_revision: Union[str, None] = "005_drop_ingest_token"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("site_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("raw_extraction_id", sa.Uuid(), nullable=True),
        sa.Column("spend_domain", sa.String(length=64), nullable=False),
        sa.Column("spend_kind", sa.String(length=128), nullable=True),
        sa.Column("issuer_name", sa.Text(), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("total_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("normalization_version", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_extraction_id"], ["document_raw_extractions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_bills_document_id"),
    )
    op.create_index("ix_bills_organization_id", "bills", ["organization_id"], unique=False)
    op.create_index("ix_bills_site_id", "bills", ["site_id"], unique=False)
    op.create_index("ix_bills_spend_domain", "bills", ["spend_domain"], unique=False)

    op.create_table(
        "bill_line_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("raw_label", sa.Text(), nullable=False),
        sa.Column("canonical_line_kind", sa.String(length=64), nullable=False),
        sa.Column("canonical_service_key", sa.String(length=128), nullable=True),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=True),
        sa.Column("quantity_unit", sa.String(length=64), nullable=True),
        sa.Column("amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["bill_id"], ["bills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bill_id", "position", name="uq_bill_line_items_bill_position"),
    )
    op.create_index("ix_bill_line_items_bill_id", "bill_line_items", ["bill_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_bill_line_items_bill_id", table_name="bill_line_items")
    op.drop_table("bill_line_items")
    op.drop_index("ix_bills_spend_domain", table_name="bills")
    op.drop_index("ix_bills_site_id", table_name="bills")
    op.drop_index("ix_bills_organization_id", table_name="bills")
    op.drop_table("bills")
