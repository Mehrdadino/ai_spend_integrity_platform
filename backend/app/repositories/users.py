"""User reads/writes for platform login (global email)."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import PlatformRole, User


def get_user_by_id(session: Session, *, user_id: uuid.UUID) -> Optional[User]:
    """Load a user by primary key."""
    return session.scalar(select(User).where(User.id == user_id))


def get_user_by_email(session: Session, *, email: str) -> Optional[User]:
    """Globally unique email lookup (login)."""
    normalized = email.strip().lower()
    return session.scalar(select(User).where(User.email == normalized))


def create_user(
    session: Session,
    *,
    email: str,
    password_hash: str,
    role: str = PlatformRole.MEMBER.value,
    organization_id: Optional[uuid.UUID] = None,
) -> User:
    """Insert a user row; caller must ``commit``."""
    user = User(
        email=email.strip().lower(),
        password_hash=password_hash,
        role=role,
        organization_id=organization_id,
    )
    session.add(user)
    session.flush()
    return user
