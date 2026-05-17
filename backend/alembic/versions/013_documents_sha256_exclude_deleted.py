"""Dedupe index: only active documents (soft-deleted rows may share sha256).

Revision ID: 013_sha256_active
Revises: 012_platform_roles
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_sha256_active"
down_revision: Union[str, None] = "012_platform_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_documents_org_sha256_not_null", table_name="documents")
    op.create_index(
        "uq_documents_org_sha256_active",
        "documents",
        ["organization_id", "sha256"],
        unique=True,
        postgresql_where=sa.text("sha256 IS NOT NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_documents_org_sha256_active", table_name="documents")
    op.create_index(
        "uq_documents_org_sha256_not_null",
        "documents",
        ["organization_id", "sha256"],
        unique=True,
        postgresql_where=sa.text("sha256 IS NOT NULL"),
    )
