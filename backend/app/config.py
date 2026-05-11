"""Centralized configuration from environment variables and ``.env``.

Uses ``pydantic-settings`` so Docker Compose defaults can be overridden per
environment (e.g. staging RDS, real S3). ``get_settings`` is cached so the
process reads env once unless the cache is cleared.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings; field names map to env vars like ``DATABASE_URL``."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Postgres DSN for SQLAlchemy (sync driver for Phase 1 simplicity).
    database_url: str = "postgresql+psycopg2://spend:spend@127.0.0.1:15432/spend_integrity"

    # S3-compatible API (MinIO locally). Originals live here; Postgres stores pointers only.
    s3_endpoint_url: str = "http://127.0.0.1:9000"
    s3_access_key_id: str = "minio"
    s3_secret_access_key: str = "minio_minio_minio"
    s3_bucket_documents: str = "documents"
    s3_region: str = "us-east-1"

    # Presigned PUT: TTL and hard cap for abuse prevention (enforced again on complete).
    presigned_upload_expires_seconds: int = 3600
    max_upload_bytes: int = 50 * 1024 * 1024

    # Comma-separated browser origins for CORS (step 1c upload UI). Empty = no CORS middleware.
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    # Redis for RQ (step 1d). Set empty to skip enqueue (document stays ``queued`` until you run worker).
    redis_url: str = "redis://127.0.0.1:6379/0"


@lru_cache
def get_settings() -> Settings:
    """Return the singleton Settings instance for this process."""
    return Settings()
