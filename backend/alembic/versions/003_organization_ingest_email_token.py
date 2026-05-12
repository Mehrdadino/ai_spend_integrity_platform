"""Add organizations.ingest_email_token for inbound-email webhook (steps 1e–1f).

Opaque per-tenant token in the webhook URL maps the MIME POST to ``organization_id``
without relying on ``X-Organization-Id`` (email providers cannot set that header on
inbound parse). NULL means email ingest is disabled for that org until a token is set.

Revision ID: 003_ingest_token
Revises: 002_presign
Create Date: 2026-05-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_ingest_token"
down_revision: Union[str, None] = "002_presign"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("ingest_email_token", sa.String(length=64), nullable=True),
    )
    # Multiple NULLs allowed: orgs without email ingest keep token unset.
    op.create_unique_constraint(
        "uq_organizations_ingest_email_token",
        "organizations",
        ["ingest_email_token"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_organizations_ingest_email_token", "organizations", type_="unique")
    op.drop_column("organizations", "ingest_email_token")
