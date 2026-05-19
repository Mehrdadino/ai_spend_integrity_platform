"""Create or upgrade a platform admin for local sign-in (no org UUID at login).

Default credentials (override via env):

- ``DEV_ADMIN_EMAIL`` (default ``admin@dev.local``)
- ``DEV_ADMIN_PASSWORD`` (default ``Dev-Admin-Change1!``)

Run from ``backend/``::

  python -m app.scripts.seed_dev_user
"""

from __future__ import annotations

import os

from app.db.session import get_session_factory
from app.models.user import PlatformRole
from app.repositories.users import create_user, get_user_by_email
from app.services.auth import hash_password


def main() -> None:
    email = os.environ.get("DEV_ADMIN_EMAIL", "admin@dev.local").strip().lower()
    password = os.environ.get("DEV_ADMIN_PASSWORD", "Dev-Admin-Change1!")
    factory = get_session_factory()
    session = factory()
    try:
        existing = get_user_by_email(session, email=email)
        if existing is not None:
            existing.role = PlatformRole.ADMIN.value
            existing.organization_id = None
            if password:
                existing.password_hash = hash_password(password)
            session.commit()
            print(f"Updated platform admin: {email} id={existing.id}")
            print("Sign in with email + password only (no organization id).")
            return
        user = create_user(
            session,
            email=email,
            password_hash=hash_password(password),
            role=PlatformRole.ADMIN.value,
            organization_id=None,
        )
        session.commit()
        print(f"Created platform admin id={user.id} email={email}")
        print("Sign in: POST /api/v1/auth/login with email + password")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
