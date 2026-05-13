"""Organization lookups, list/create for HTTP (dev), and idempotent ``ensure`` for CLI."""

from __future__ import annotations

import re
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization

# URL-safe tenant key (lowercase); Postgres unique index on ``slug``.
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class OrganizationSlugConflictError(Exception):
    """Another row already owns this ``slug`` (``POST /organizations`` should map to 409)."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"Organization slug already exists: {slug!r}")


def get_organization_by_id(session: Session, organization_id: uuid.UUID) -> Optional[Organization]:
    """Primary key fetch (used by ``X-Organization-Id`` dependency)."""
    return session.scalar(select(Organization).where(Organization.id == organization_id))


def get_organization_by_slug(session: Session, slug: str) -> Optional[Organization]:
    """Stable slug lookup (e.g. ``dev`` for local seeds); ``slug`` is matched case-insensitively."""
    key = slug.strip().lower()
    return session.scalar(select(Organization).where(Organization.slug == key))


def ensure_organization(session: Session, *, name: str, slug: str) -> Organization:
    """Return existing org by slug or insert a new one (caller commits)."""
    org = get_organization_by_slug(session, slug.strip().lower())
    if org:
        return org
    org = Organization(id=uuid.uuid4(), name=name.strip(), slug=slug.strip().lower())
    session.add(org)
    session.flush()
    return org


def list_organizations(session: Session, *, limit: int = 500) -> list[Organization]:
    """All tenants (newest first); used by the dev admin list endpoint — no org filter."""
    rows = session.scalars(
        select(Organization).order_by(Organization.created_at.desc()).limit(limit)
    ).all()
    return list(rows)


def create_organization(session: Session, *, name: str, slug: str) -> Organization:
    """Insert a new organization; raises ``OrganizationSlugConflictError`` if ``slug`` is taken.

    Normalizes ``slug`` to lowercase for storage and lookup consistency with ``ensure_organization``.
    """
    normalized = slug.strip().lower()
    if not normalized or not _SLUG_PATTERN.fullmatch(normalized):
        raise ValueError(
            "slug must be non-empty lowercase letters, digits, and single hyphens between segments"
        )
    if get_organization_by_slug(session, normalized) is not None:
        raise OrganizationSlugConflictError(normalized)
    org = Organization(id=uuid.uuid4(), name=name.strip(), slug=normalized)
    session.add(org)
    session.flush()
    return org
