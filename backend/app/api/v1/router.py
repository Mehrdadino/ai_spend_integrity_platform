"""Aggregate all v1 routers under a single ``APIRouter`` for ``app.main``."""

from fastapi import APIRouter

from app.api.v1 import documents, webhooks_inbound_email

api_router = APIRouter()
api_router.include_router(documents.router)
api_router.include_router(webhooks_inbound_email.router)
