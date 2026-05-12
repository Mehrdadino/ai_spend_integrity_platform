"""S3-compatible object storage helpers (MinIO locally, AWS S3 in production).

All document bytes are stored via this module; Postgres only stores ``bucket``
and ``object_key`` plus metadata. Presigned URLs must use the same
``Content-Type`` as signed, or MinIO/AWS will reject the client PUT.
"""

import hashlib
import logging

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)


def get_s3_client():
    """Build a boto3 S3 client from ``Settings`` (endpoint for MinIO override)."""
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )


def ensure_documents_bucket_exists() -> None:
    """Create the configured documents bucket if missing (idempotent for dev)."""
    settings = get_settings()
    client = get_s3_client()
    name = settings.s3_bucket_documents
    try:
        client.head_bucket(Bucket=name)
        logger.info("Object storage bucket exists: %s", name)
        return
    except ClientError:
        # Bucket missing or first-run; attempt creation.
        logger.info("Creating object storage bucket: %s", name)
    try:
        client.create_bucket(Bucket=name)
    except ClientError as e:
        # Concurrent startup or already created by another process.
        if e.response.get("Error", {}).get("Code") != "BucketAlreadyOwnedByYou":
            raise


def put_document_object(*, bucket: str, key: str, body: bytes, content_type: str) -> None:
    """Server-side upload of full body (used by CLI / direct ingestion path)."""
    client = get_s3_client()
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)


def delete_document_object(*, bucket: str, key: str) -> None:
    """Remove an object (e.g. compensate after failed DB insert)."""
    client = get_s3_client()
    client.delete_object(Bucket=bucket, Key=key)


def generate_presigned_get_url(
    *,
    bucket: str,
    key: str,
    expires_in: int,
    response_content_type: str | None = None,
) -> str:
    """Return a time-limited URL for GET (browser ``iframe`` / ``img`` preview).

    Optional ``response_content_type`` is signed into the URL so MinIO/S3 returns
    the correct ``Content-Type`` for PDF rendering in embedded viewers.
    """
    client = get_s3_client()
    params: dict[str, str] = {"Bucket": bucket, "Key": key}
    if response_content_type:
        params["ResponseContentType"] = response_content_type
    return client.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=expires_in,
        HttpMethod="GET",
    )


def generate_presigned_put_url(
    *,
    bucket: str,
    key: str,
    content_type: str,
    expires_in: int,
) -> str:
    """Return a time-limited URL for the browser or curl to PUT bytes directly."""
    client = get_s3_client()
    return client.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
        HttpMethod="PUT",
    )


def head_document_object(*, bucket: str, key: str) -> dict:
    """Return S3 head response metadata (optional helper for size/ETag checks)."""
    client = get_s3_client()
    return client.head_object(Bucket=bucket, Key=key)


def sha256_and_size_from_object(*, bucket: str, key: str) -> tuple[str, int]:
    """Stream the object from storage and compute SHA-256 and total size (trusted finalize)."""
    client = get_s3_client()
    resp = client.get_object(Bucket=bucket, Key=key)
    body = resp["Body"]
    h = hashlib.sha256()
    total = 0
    for chunk in body.iter_chunks(chunk_size=1024 * 1024):
        h.update(chunk)
        total += len(chunk)
    return h.hexdigest(), total
