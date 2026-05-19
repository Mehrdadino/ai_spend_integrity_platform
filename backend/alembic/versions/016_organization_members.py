"""Per-org membership and email invites (B2B team model).

Revision ID: 016_organization_members
Revises: 015_auth_challenges
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016_organization_members"
down_revision: Union[str, None] = "015_auth_challenges"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_org_members_org_user"),
    )
    op.create_index("ix_org_members_organization_id", "organization_members", ["organization_id"])
    op.create_index("ix_org_members_user_id", "organization_members", ["user_id"])

    op.create_table(
        "organization_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_org_invites_organization_id", "organization_invites", ["organization_id"])
    op.create_index("ix_org_invites_email", "organization_invites", ["email"])

    # Backfill: org creators become org_admin members.
    op.execute(
        """
        INSERT INTO organization_members (id, organization_id, user_id, role)
        SELECT gen_random_uuid(), o.id, o.created_by_user_id, 'org_admin'
        FROM organizations o
        WHERE o.created_by_user_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_org_invites_email", table_name="organization_invites")
    op.drop_index("ix_org_invites_organization_id", table_name="organization_invites")
    op.drop_table("organization_invites")
    op.drop_index("ix_org_members_user_id", table_name="organization_members")
    op.drop_index("ix_org_members_organization_id", table_name="organization_members")
    op.drop_table("organization_members")
