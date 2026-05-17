"""Pydantic request/response models for document HTTP endpoints (OpenAPI schema)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.document_display_name import normalize_display_name


class PresignedUploadRequest(BaseModel):
    """Client declares MIME type (signed into URL); optional site, label, and size hint."""

    mime_type: str = Field(..., max_length=255, examples=["application/pdf"])
    site_id: Optional[UUID] = None
    display_name: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional user label; omit or send blank to leave unset.",
    )
    expected_byte_size: Optional[int] = Field(None, ge=0)

    @field_validator("display_name", mode="before")
    @classmethod
    def _normalize_display_name(cls, value: object) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            return normalize_display_name(value)
        return value  # type: ignore[return-value]


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


class DeleteDocumentResponse(BaseModel):
    """Acknowledgement after soft delete (row kept for future hard delete / audit)."""

    document_id: UUID
    deleted_at: datetime


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


class PatchDocumentDisplayNameRequest(BaseModel):
    """Set or clear the optional user label (null or blank clears)."""

    display_name: Optional[str] = Field(
        None,
        max_length=255,
        description="User label, or null/blank to remove.",
    )

    @field_validator("display_name", mode="before")
    @classmethod
    def _normalize_display_name(cls, value: object) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            return normalize_display_name(value)
        return value  # type: ignore[return-value]


class PatchDocumentDisplayNameResponse(BaseModel):
    """Echo document id and effective display name after PATCH."""

    document_id: UUID
    display_name: Optional[str] = None


class DocumentDetailResponse(BaseModel):
    """Single document row for the upload UI / detail (1c + 1h + 2a summary)."""

    document_id: UUID
    organization_id: UUID
    display_name: Optional[str] = None
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


class PatchDocumentSiteRequest(BaseModel):
    """Assign or clear the facility/site for a document (and its bill, if present)."""

    site_id: Optional[UUID] = Field(
        None,
        description="Site UUID under this org, or null to clear.",
    )


class PatchDocumentSiteResponse(BaseModel):
    """Echo document id and effective site after assignment."""

    document_id: UUID
    site_id: Optional[UUID] = None


class DocumentListItemResponse(BaseModel):
    """One row for ``GET /documents`` (step 1h): status + optional worker error."""

    document_id: UUID
    display_name: Optional[str] = None
    site_id: Optional[UUID] = None
    mime_type: str
    byte_size: Optional[int] = None
    sha256: Optional[str] = None
    source: str
    processing_status: str
    processing_error: Optional[str] = None
    anomaly_review_status: Optional[str] = Field(
        None,
        description=(
            "Rollup of ``anomalies.review_status`` for this document "
            "(flagged > open > dismissed > approved); null when no anomalies."
        ),
    )
    created_at: datetime


class DocumentBrowseResponse(BaseModel):
    """Paginated document search for anomaly inbox / pickers (``GET /documents/browse``)."""

    items: list[DocumentListItemResponse]
    total: int = Field(..., ge=0)
    offset: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
