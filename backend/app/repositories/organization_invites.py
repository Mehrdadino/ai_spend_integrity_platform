"""Pending organization invites (email + hashed token)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.organization_invite import OrganizationInvite
from app.services.auth.passwords import verify_password


def list_pending_invites_for_organization(
    session: Session,
    *,
    organization_id: uuid.UUID,
) -> list[OrganizationInvite]:
    """Unaccepted invites that have not expired."""
    now = datetime.now(timezone.utc)
    rows = session.scalars(
        select(OrganizationInvite)
        .where(
            OrganizationInvite.organization_id == organization_id,
            OrganizationInvite.accepted_at.is_(None),
            OrganizationInvite.expires_at > now,
        )
        .order_by(OrganizationInvite.created_at.desc())
    ).all()
    return list(rows)


def list_open_invites_for_organization(
    session: Session,
    *,
    organization_id: uuid.UUID,
) -> list[OrganizationInvite]:
    """Unaccepted invites (pending or expired) for team directory status."""
    rows = session.scalars(
        select(OrganizationInvite)
        .where(
            OrganizationInvite.organization_id == organization_id,
            OrganizationInvite.accepted_at.is_(None),
        )
        .order_by(OrganizationInvite.created_at.desc())
    ).all()
    return list(rows)


def find_pending_invite_by_token(
    session: Session,
    *,
    token: str,
) -> Optional[OrganizationInvite]:
    """Match plaintext invite token against active pending invites."""
    now = datetime.now(timezone.utc)
    rows = session.scalars(
        select(OrganizationInvite)
        .where(
            OrganizationInvite.accepted_at.is_(None),
            OrganizationInvite.expires_at > now,
        )
        .options(joinedload(OrganizationInvite.organization))
    ).all()
    for row in rows:
        if verify_password(token.strip(), row.token_hash):
            return row
    return None


def create_organization_invite(
    session: Session,
    *,
    organization_id: uuid.UUID,
    email: str,
    role: str,
    token_hash: str,
    invited_by_user_id: uuid.UUID,
    expires_at: datetime,
) -> OrganizationInvite:
    """Persist a new invite; caller emails the plaintext token."""
    row = OrganizationInvite(
        organization_id=organization_id,
        email=email.strip().lower(),
        role=role,
        token_hash=token_hash,
        invited_by_user_id=invited_by_user_id,
        expires_at=expires_at,
    )
    session.add(row)
    session.flush()
    return row


def mark_invite_accepted(session: Session, invite: OrganizationInvite) -> None:
    """Mark invite redeemed."""
    invite.accepted_at = datetime.now(timezone.utc)
    session.flush()
