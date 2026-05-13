"""Remove ``organizations.ingest_email_token`` (inbound email ingest retired).

The product no longer ships the multipart webhook path; tenancy stays
``X-Organization-Id`` + presigned upload / CLI registration only.

Revision ID: 005_drop_ingest_token
Revises: 004_raw_extraction
Create Date: 2026-05-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_drop_ingest_token"
down_revision: Union[str, None] = "004_raw_extraction"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_organizations_ingest_email_token", "organizations", type_="unique")
    op.drop_column("organizations", "ingest_email_token")


def downgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("ingest_email_token", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_organizations_ingest_email_token",
        "organizations",
        ["ingest_email_token"],
    )
