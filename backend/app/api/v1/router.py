"""Aggregate all v1 routers under a single ``APIRouter`` for ``app.main``."""

from fastapi import APIRouter

from app.api.v1 import documents

api_router = APIRouter()
api_router.include_router(documents.router)
