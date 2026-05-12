"""Pydantic request/response models for document HTTP endpoints (OpenAPI schema)."""

from __future__ import annotations

from datetime import datetime
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
    """Row is ``queued``; RQ worker moves it to ``received`` (step 1d) before extraction."""

    document_id: UUID
    sha256: str
    byte_size: int
    processing_status: str


class DocumentDetailResponse(BaseModel):
    """Single document row for the upload UI / future document detail page (step 1c)."""

    document_id: UUID
    organization_id: UUID
    site_id: Optional[UUID] = None
    bucket: str
    object_key: str
    sha256: Optional[str] = None
    mime_type: str
    byte_size: Optional[int] = None
    source: str
    processing_status: str
    created_at: datetime


class DocumentListItemResponse(BaseModel):
    """One row for ``GET /documents`` (step 1h): status-focused, no storage internals."""

    document_id: UUID
    site_id: Optional[UUID] = None
    mime_type: str
    byte_size: Optional[int] = None
    sha256: Optional[str] = None
    source: str
    processing_status: str
    created_at: datetime
