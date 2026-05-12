"""Response models for the inbound-email webhook (step 1e)."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class InboundEmailDocumentResult(BaseModel):
    """One attachment outcome: new row or duplicate hash for the same org."""

    document_id: uuid.UUID
    outcome: Literal["created", "duplicate"] = Field(
        description="created=new S3 object + row; duplicate=existing org+sha256 row reused",
    )


class InboundEmailWebhookResponse(BaseModel):
    """JSON returned to the email provider (often ignores body; 200 stops retries)."""

    results: list[InboundEmailDocumentResult] = Field(default_factory=list)
