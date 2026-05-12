"""Organization lookups and idempotent ``ensure`` helpers for dev/CLI.

Includes ingest-token resolution for the inbound-email webhook (step 1f).
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization


def get_organization_by_id(session: Session, organization_id: uuid.UUID) -> Optional[Organization]:
    """Primary key fetch (used by ``X-Organization-Id`` dependency)."""
    return session.scalar(select(Organization).where(Organization.id == organization_id))


def get_organization_by_slug(session: Session, slug: str) -> Optional[Organization]:
    """Stable slug lookup (e.g. ``dev`` for local seeds)."""
    return session.scalar(select(Organization).where(Organization.slug == slug))


def get_organization_by_ingest_email_token(session: Session, token: str) -> Optional[Organization]:
    """Resolve tenant for inbound-email multipart POST (step 1f); token must match exactly."""
    if not token:
        return None
    return session.scalar(select(Organization).where(Organization.ingest_email_token == token))


def ensure_organization(session: Session, *, name: str, slug: str) -> Organization:
    """Return existing org by slug or insert a new one (caller commits)."""
    org = get_organization_by_slug(session, slug)
    if org:
        return org
    org = Organization(id=uuid.uuid4(), name=name, slug=slug)
    session.add(org)
    session.flush()
    return org
