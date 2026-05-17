"""Optional user-facing label on documents (upload or later edit).

Revision ID: 014_doc_display_name
Revises: 013_sha256_active
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "014_doc_display_name"
down_revision: Union[str, None] = "013_sha256_active"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("display_name", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "display_name")
