"""Pydantic request/response models for document upload endpoints (OpenAPI schema)."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PresignedUploadRequest(BaseModel):
    """Client declares MIME type (signed into URL); optional site and size hint."""

    mime_type: str = Field(..., max_length=255, examples=["application/pdf"])
    site_id: Optional[UUID] = None
    expected_byte_size: Optional[int] = Field(None, ge=0)


class PresignedUploadResponse(BaseModel):
    """Everything needed to PUT the file, including mandatory Content-Type header."""

    document_id: UUID
    bucket: str
    object_key: str
    upload_url: str
    upload_method: str = "PUT"
    headers: dict[str, str]
    expires_in_seconds: int


class CompleteUploadResponse(BaseModel):
    """Row is now ``pending`` and ready for downstream extraction (step 1d)."""

    document_id: UUID
    sha256: str
    byte_size: int
    processing_status: str
