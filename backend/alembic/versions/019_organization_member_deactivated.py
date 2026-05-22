"""Soft-deactivate org members (retain roster history + deactivated_by).

Revision ID: 019_org_member_deactivated
Revises: 018_documents_unsupported_code
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019_org_member_deactivated"
down_revision: Union[str, None] = "018_documents_unsupported_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organization_members",
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "organization_members",
        sa.Column("deactivated_by_user_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_org_members_deactivated_by_user",
        "organization_members",
        "users",
        ["deactivated_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_org_members_deactivated_by_user", "organization_members", type_="foreignkey")
    op.drop_column("organization_members", "deactivated_by_user_id")
    op.drop_column("organization_members", "deactivated_at")
