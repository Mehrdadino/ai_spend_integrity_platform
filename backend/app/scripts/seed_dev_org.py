"""Insert a fixed dev ``Organization`` row if missing (local / CI convenience).

Uses a stable UUID so ``frontend/.env`` can match after a fresh migrate.
If ``slug=dev`` already exists (e.g. from ``register-document``), prints that row
and does not overwrite.

Run from ``backend/``::

  seed-dev-org
"""

from __future__ import annotations

import uuid

from app.db.session import get_session_factory
from app.models.organization import Organization
from app.repositories.organizations import get_organization_by_slug

# Stable dev tenant id (use as ``VITE_ORG_ID`` / ``X-Organization-Id`` on new DBs).
DEV_ORGAN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEV_SLUG = "dev"
DEV_NAME = "Dev Organization"


def main() -> None:
    """Create ``dev`` org with ``DEV_ORGAN_ID`` or print existing ``dev`` org id."""
    factory = get_session_factory()
    session = factory()
    try:
        existing = get_organization_by_slug(session, DEV_SLUG)
        if existing is not None:
            print(f"Already exists: slug={DEV_SLUG} id={existing.id}")
            print(f"Use as VITE_ORG_ID / X-Organization-Id: {existing.id}")
            return
        org = Organization(id=DEV_ORGAN_ID, name=DEV_NAME, slug=DEV_SLUG)
        session.add(org)
        session.commit()
        print(f"Created: slug={DEV_SLUG} id={DEV_ORGAN_ID}")
        print(f"Use as VITE_ORG_ID / X-Organization-Id: {DEV_ORGAN_ID}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
