"""FastAPI dependencies that apply auth rate limits by client IP."""

from __future__ import annotations

from fastapi import Request

from app.services.rate_limit import enforce_rate_limit_ip


def rate_limit_auth_ip(action: str):
    """Build a dependency that rate-limits ``action`` per client IP."""

    async def _dependency(request: Request) -> None:
        enforce_rate_limit_ip(request, action)

    return _dependency
