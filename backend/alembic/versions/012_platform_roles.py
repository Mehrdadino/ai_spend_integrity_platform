"""Platform roles: global user email, nullable home org, org creator tracking.

Revision ID: 012_platform_roles
Revises: 011_user_auth_rbac
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_platform_roles"
down_revision: Union[str, None] = "011_user_auth_rbac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_organizations_created_by_user",
        "organizations",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_organizations_created_by_user_id",
        "organizations",
        ["created_by_user_id"],
        unique=False,
    )

    # ``role`` becomes platform-wide admin/member (not per-org).
    op.alter_column("users", "organization_id", nullable=True)
    op.drop_constraint("uq_users_org_email", "users", type_="unique")
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.create_unique_constraint("uq_users_org_email", "users", ["organization_id", "email"])
    op.alter_column("users", "organization_id", nullable=False)

    op.drop_index("ix_organizations_created_by_user_id", table_name="organizations")
    op.drop_constraint("fk_organizations_created_by_user", "organizations", type_="foreignkey")
    op.drop_column("organizations", "created_by_user_id")
