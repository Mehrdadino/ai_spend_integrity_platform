"""Add ``documents.deleted_at`` for soft delete (hidden from UI list/viewer).

Hard delete of object storage bytes is a later step; this migration only marks rows.

Revision ID: 007_documents_deleted_at
Revises: 006_bills_lines
Create Date: 2026-05-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_documents_deleted_at"
down_revision: Union[str, None] = "006_bills_lines"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_documents_deleted_at",
        "documents",
        ["deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_documents_deleted_at", table_name="documents")
    op.drop_column("documents", "deleted_at")
