"""Pydantic request/response models for document HTTP endpoints (OpenAPI schema)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
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
    """Row is ``queued``; worker advances through ``received`` / ``extracted`` (2a) or ``failed``."""

    document_id: UUID
    sha256: str
    byte_size: int
    processing_status: str
    processing_error: Optional[str] = None


class ReprocessDocumentResponse(BaseModel):
    """Same status fields as list/detail after requeue: ``queued`` until the worker runs."""

    document_id: UUID
    processing_status: str
    processing_error: Optional[str] = None


class RawExtractionSnapshotResponse(BaseModel):
    """Latest ``document_raw_extractions`` row for GET detail (debug / support)."""

    extraction_id: UUID
    model_id: Optional[str] = None
    extraction_version: Optional[str] = None
    created_at: datetime
    raw_payload: dict[str, Any]


class DocumentReadUrlResponse(BaseModel):
    """Time-limited GET URL for the stored original (browser ``iframe`` / ``img``)."""

    read_url: str
    expires_in_seconds: int
    mime_type: str


class DocumentDetailResponse(BaseModel):
    """Single document row for the upload UI / detail (1c + 1h + 2a summary)."""

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
    processing_error: Optional[str] = None
    created_at: datetime
    latest_raw_extraction: Optional[RawExtractionSnapshotResponse] = None


class DocumentViewerResponse(DocumentDetailResponse):
    """Detail plus presigned read URL so one round-trip can drive the viewer UI."""

    read_url: str
    read_url_expires_in_seconds: int


class DocumentListItemResponse(BaseModel):
    """One row for ``GET /documents`` (step 1h): status + optional worker error."""

    document_id: UUID
    site_id: Optional[UUID] = None
    mime_type: str
    byte_size: Optional[int] = None
    sha256: Optional[str] = None
    source: str
    processing_status: str
    processing_error: Optional[str] = None
    created_at: datetime
