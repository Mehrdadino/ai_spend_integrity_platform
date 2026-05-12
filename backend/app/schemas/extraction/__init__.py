"""Strict schemas for persisted raw extraction JSON (pillar 2b).

Each ``extraction_version`` (e.g. ``stub-v1``) maps to a Pydantic model used before
JSONB insert. There is **no** repair path: invalid payloads fail validation and the
worker marks the document ``failed``.
"""

from app.schemas.extraction.stub_payload import StubRawExtractionPayload

__all__ = ["StubRawExtractionPayload"]
