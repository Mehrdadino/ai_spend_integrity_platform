"""FastAPI dependencies shared across routers (tenant resolution, DB session).

``X-Organization-Id`` is a temporary stand-in for real auth (JWT / session);
it must be a UUID of an existing ``Organization`` row.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.organization import Organization
from app.repositories.organizations import get_organization_by_id


def require_organization(
    x_organization_id: Annotated[str, Header(alias="X-Organization-Id")],
    db: Session = Depends(get_db),
) -> Organization:
    """Resolve the tenant from ``X-Organization-Id`` or return 400/404."""
    try:
        org_id = UUID(x_organization_id.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid X-Organization-Id") from e
    org = get_organization_by_id(db, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org
