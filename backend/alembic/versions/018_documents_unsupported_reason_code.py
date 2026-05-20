"""Stable code for ``unsupported`` rows (UI hints: re-upload vs reprocess same file).

Revision ID: 018_documents_unsupported_code
Revises: 017_documents_unsupported
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018_documents_unsupported_code"
down_revision: Union[str, None] = "017_documents_unsupported"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("unsupported_reason_code", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "unsupported_reason_code")
