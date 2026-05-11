"""Presigned upload: nullable sha256/byte_size until complete; partial unique on sha256.

Revision ID: 002_presign
Revises: 001_initial
Create Date: 2026-05-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_presign"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Allow in-flight presigned uploads (sha256 unknown); dedupe once hash is set.
    op.drop_constraint("uq_documents_org_sha256", "documents", type_="unique")
    op.alter_column("documents", "sha256", existing_type=sa.String(length=64), nullable=True)
    op.alter_column("documents", "byte_size", existing_type=sa.BigInteger(), nullable=True)
    op.create_index(
        "uq_documents_org_sha256_not_null",
        "documents",
        ["organization_id", "sha256"],
        unique=True,
        postgresql_where=sa.text("sha256 IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_documents_org_sha256_not_null", table_name="documents")
    op.execute(sa.text("DELETE FROM documents WHERE sha256 IS NULL OR byte_size IS NULL"))
    op.alter_column("documents", "byte_size", existing_type=sa.BigInteger(), nullable=False)
    op.alter_column("documents", "sha256", existing_type=sa.String(length=64), nullable=False)
    op.create_unique_constraint("uq_documents_org_sha256", "documents", ["organization_id", "sha256"])
