"""Site queries scoped by organization (tenant isolation)."""

from __future__ import annotations

import uuid
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.site import Site


def get_site_for_organization(
    session: Session, site_id: UUID, organization_id: UUID
) -> Optional[Site]:
    """Return site only if it belongs to the given org (prevents cross-tenant links)."""
    return session.scalar(
        select(Site).where(Site.id == site_id, Site.organization_id == organization_id)
    )


def get_site_by_org_and_name(session: Session, organization_id: UUID, name: str) -> Optional[Site]:
    """Human-readable site lookup within one org."""
    return session.scalar(
        select(Site).where(Site.organization_id == organization_id, Site.name == name)
    )


def list_sites_for_organization(
    session: Session,
    *,
    organization_id: UUID,
    limit: int = 200,
) -> list[Site]:
    """Alphabetical site list for upload/viewer pickers (tenant-scoped)."""
    stmt = (
        select(Site)
        .where(Site.organization_id == organization_id)
        .order_by(Site.name.asc())
        .limit(max(1, min(limit, 500)))
    )
    return list(session.scalars(stmt).all())


def ensure_site(session: Session, *, organization_id: UUID, name: str) -> Site:
    """Idempotent create by (org, name) for dev/CLI."""
    site = get_site_by_org_and_name(session, organization_id, name)
    if site:
        return site
    site = Site(id=uuid.uuid4(), organization_id=organization_id, name=name)
    session.add(site)
    session.flush()
    return site
