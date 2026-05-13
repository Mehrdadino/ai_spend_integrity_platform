"""Aggregate all v1 routers under a single ``APIRouter`` for ``app.main``.

Order: ``organizations`` before ``documents`` so path registration stays predictable;
paths do not overlap (``/organizations`` vs ``/documents``).
"""

from fastapi import APIRouter

from app.api.v1 import documents, organizations

api_router = APIRouter()
api_router.include_router(organizations.router)
api_router.include_router(documents.router)
