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
    # Presigned GET: browser preview of stored originals (API still enforces org scope).
    presigned_read_expires_seconds: int = 3600
    max_upload_bytes: int = 50 * 1024 * 1024

    # Comma-separated browser origins for CORS (step 1c upload UI). Empty = no CORS middleware.
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    # Redis for RQ (step 1d). Set empty to skip enqueue (document stays ``queued`` until you run worker).
    redis_url: str = "redis://127.0.0.1:6379/0"

    # Recorded on ``document_raw_extractions.model_id`` when no LLM is configured.
    raw_extraction_stub_model_id: str = "stub-llm"

    # Optional OpenAI-compatible ``/chat/completions`` for ``generic-bill-v1`` (worker).
    # Empty ``extraction_llm_api_key`` → deterministic extraction only.
    extraction_llm_api_key: str = ""
    extraction_llm_base_url: str = "https://api.openai.com/v1"
    extraction_llm_model: str = "gpt-4o-mini"
    extraction_llm_timeout_seconds: int = 90

    # PDF embedded-text extraction (pypdf) before LLM structuring; OCR is a separate future path.
    extraction_text_min_chars_total: int = 40
    extraction_text_min_chars_per_page: int = 25
    extraction_llm_max_document_chars: int = 24_000

    # OCR (Phase 1): local/free Tesseract for scan-only PDFs / image bills.
    # This uses embedded PDFs first; OCR is only attempted when embedded text
    # is too sparse.
    ocr_provider: str = "tesseract"
    ocr_tesseract_lang: str = "eng"
    ocr_dpi: int = 300
    ocr_max_pages: int = 10

    # P1 auth: JWT is the primary tenant + user context for org-scoped routes.
    # Set ``auth_allow_dev_org_header=true`` to keep ``X-Organization-Id`` for scripts/CI.
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    # JWT lifetime: short session vs 30-day "remember this device" (login checkbox).
    jwt_session_expire_minutes: int = 12 * 60
    jwt_remember_expire_minutes: int = 30 * 24 * 60
    auth_allow_dev_org_header: bool = True
    # Sign-up, email 2FA, and password reset (P1 extension).
    auth_allow_registration: bool = True
    auth_otp_expire_minutes: int = 10
    auth_reset_expire_minutes: int = 60
    # Base URL for links in password-reset emails (Vite dev server by default).
    auth_frontend_base_url: str = "http://127.0.0.1:5173"
    # SMTP: leave host empty to log auth emails to the API process (local dev).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@spend-integrity.local"
    smtp_use_tls: bool = True

    # P3 org bootstrap: when set, ``GET/POST /organizations`` require this header value.
    org_bootstrap_token: str = ""

    # §3e: keyset page size when walking very long site histories in one RQ job.
    site_bill_keyset_page_size: int = 200
    # Safety cap on bills processed per site-wide refresh job (0 = unlimited).
    site_bill_refresh_max_bills: int = 10_000


@lru_cache
def get_settings() -> Settings:
    """Return the singleton Settings instance for this process."""
    return Settings()
