"""Add ``documents.processing_error`` and ``document_raw_extractions`` (2a).

``processing_error`` stores a short worker/API failure message for the list UI.
``document_raw_extractions`` appends versioned LLM JSON blobs per ``document_id``
(Postgres JSONB); the worker currently writes a deterministic stub until a real
model is wired.

Revision ID: 004_raw_extraction
Revises: 003_ingest_token
Create Date: 2026-05-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_raw_extraction"
down_revision: Union[str, None] = "003_ingest_token"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("processing_error", sa.Text(), nullable=True),
    )
    op.create_table(
        "document_raw_extractions",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=True),
        sa.Column("extraction_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_document_raw_extractions_document_id"),
        "document_raw_extractions",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_document_raw_extractions_document_id"), table_name="document_raw_extractions")
    op.drop_table("document_raw_extractions")
    op.drop_column("documents", "processing_error")
