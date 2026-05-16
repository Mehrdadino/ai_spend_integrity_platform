"""P1/P3: user password hash + org role for JWT auth and minimal RBAC.

Revision ID: 011_user_auth_rbac
Revises: 010_bills_site_period
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_user_auth_rbac"
down_revision: Union[str, None] = "010_bills_site_period"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=32), nullable=False, server_default="member"),
    )
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )
    # Drop server default so application owns the default on new rows.
    op.alter_column("users", "role", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "password_hash")
    op.drop_column("users", "role")
