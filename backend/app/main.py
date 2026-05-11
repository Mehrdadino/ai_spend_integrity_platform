"""FastAPI application entry: HTTP API, lifespan hooks, and health checks.

Mounts versioned routers under ``/api/v1``. On startup, ensures the documents
S3 bucket exists so uploads (presigned or server-side) do not fail mid-request.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.router import api_router as api_v1_router
from app.config import get_settings
from app.db.session import get_db
from app.services.storage import ensure_documents_bucket_exists, get_s3_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Provision dev-friendly object storage (bucket) before accepting traffic."""
    ensure_documents_bucket_exists()
    yield


app = FastAPI(title="Spend Integrity API", version="0.1.0", lifespan=lifespan)
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health")
def health():
    """Liveness: process is up (no dependency checks)."""
    return {"status": "ok"}


@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness: Postgres responds and the documents bucket is reachable."""
    db.execute(text("SELECT 1"))
    settings = get_settings()
    # head_bucket verifies credentials and bucket presence (MinIO or AWS).
    get_s3_client().head_bucket(Bucket=settings.s3_bucket_documents)
    return {"status": "ready", "database": "ok", "object_storage": "ok"}
