"""Add ``unsupported_reason`` for non-utility uploads (status ``unsupported``).

Revision ID: 017_documents_unsupported
Revises: 016_organization_members
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017_documents_unsupported"
down_revision: Union[str, None] = "016_organization_members"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("unsupported_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "unsupported_reason")
