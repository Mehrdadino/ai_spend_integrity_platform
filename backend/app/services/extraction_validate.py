"""Validate raw extraction dicts before JSONB insert (step 2b). No repair: invalid → raise.

Callers (e.g. ``raw_extraction`` service) catch ``ExtractionPayloadValidationError`` and
map it to ``documents.processing_error`` + ``failed`` status.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.constants.extraction import STUB_EXTRACTION_VERSION
from app.schemas.extraction.stub_payload import StubRawExtractionPayload

logger = logging.getLogger(__name__)


class ExtractionPayloadValidationError(Exception):
    """Payload failed strict Pydantic validation; message is safe to store on ``documents``."""

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


def _format_pydantic_errors(exc: ValidationError) -> str:
    """Compact JSON for logs and ``processing_error`` (bounded length)."""
    try:
        body = json.dumps(exc.errors(), default=str)[:6000]
    except Exception:
        body = str(exc)[:6000]
    return f"Pydantic validation failed: {body}"


def validate_raw_extraction_payload(
    payload: dict[str, Any],
    *,
    extraction_version: str,
    expected_document_id: UUID,
) -> dict[str, Any]:
    """Return JSON-serializable dict for ``raw_payload`` after strict validation.

    ``expected_document_id`` must match ``document_id`` inside the payload (defense
    against accidental cross-document writes). No mutation of invalid input.
    """
    if extraction_version == STUB_EXTRACTION_VERSION:
        try:
            model = StubRawExtractionPayload.model_validate(payload)
        except ValidationError as exc:
            msg = _format_pydantic_errors(exc)
            logger.warning("extraction_validate: stub payload invalid: %s", msg[:500])
            raise ExtractionPayloadValidationError(msg) from exc
        if model.document_id != expected_document_id:
            raise ExtractionPayloadValidationError(
                f"document_id in payload ({model.document_id}) does not match document ({expected_document_id})"
            )
        return model.model_dump(mode="json")

    raise ExtractionPayloadValidationError(
        f"No Pydantic schema registered for extraction_version={extraction_version!r}"
    )
