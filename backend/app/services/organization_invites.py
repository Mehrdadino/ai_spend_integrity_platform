"""Create and accept organization invites (email + membership)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.organization_invite import OrganizationInvite
from app.models.organization_member import OrgMemberRole
from app.models.user import PlatformRole, User
from app.repositories.organization_invites import (
    create_organization_invite,
    find_pending_invite_by_token,
    mark_invite_accepted,
)
from app.repositories.organization_members import (
    add_organization_member,
    get_membership,
    is_active_member,
)
from app.repositories.users import create_user, get_user_by_email
from app.services.auth.email_delivery import send_auth_email
from app.services.auth.passwords import hash_password
from app.services.auth.secrets import generate_password_reset_token


class InviteError(ValueError):
    """Invalid or expired invite, or email mismatch."""


@dataclass(frozen=True)
class InviteCreated:
    """Plain token for the email link (stored hashed in DB)."""

    invite_id: uuid.UUID
    invite_token: str


@dataclass(frozen=True)
class InvitePreview:
    """Safe metadata for the invite landing page (no token)."""

    email: str
    organization_id: uuid.UUID
    organization_name: str
    role: str
    account_exists: bool


def _valid_org_role(role: str) -> str:
    allowed = {r.value for r in OrgMemberRole}
    normalized = role.strip().lower()
    if normalized not in allowed:
        raise ValueError(f"role must be one of: {', '.join(sorted(allowed))}")
    return normalized


def create_invite(
    session: Session,
    *,
    organization_id: uuid.UUID,
    email: str,
    role: str,
    invited_by: User,
) -> InviteCreated:
    """Email an invite link; existing members for that email are rejected."""
    role = _valid_org_role(role)
    normalized_email = email.strip().lower()
    existing_user = get_user_by_email(session, email=normalized_email)
    if existing_user is not None:
        existing_membership = get_membership(
            session,
            organization_id=organization_id,
            user_id=existing_user.id,
        )
        if is_active_member(existing_membership):
            raise InviteError("That user is already a member of this organization")

    settings = get_settings()
    token = generate_password_reset_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.org_invite_expire_days)
    invite = create_organization_invite(
        session,
        organization_id=organization_id,
        email=normalized_email,
        role=role,
        token_hash=hash_password(token),
        invited_by_user_id=invited_by.id,
        expires_at=expires_at,
    )
    accept_url = f"{settings.auth_frontend_base_url.rstrip('/')}/?invite_token={token}"
    send_auth_email(
        to_email=normalized_email,
        subject="You're invited to Spend Integrity",
        body_text=(
            f"You have been invited to join an organization on Spend Integrity.\n\n"
            f"Set your password and join using this link:\n"
            f"{accept_url}\n\n"
            f"This invite expires in {settings.org_invite_expire_days} days."
        ),
    )
    return InviteCreated(invite_id=invite.id, invite_token=token)


def preview_invite(session: Session, *, token: str) -> InvitePreview:
    """Resolve invite token to org context for the activation UI."""
    invite = find_pending_invite_by_token(session, token=token)
    if invite is None:
        raise InviteError("Invalid or expired invite link")
    org = invite.organization
    if org is None:
        raise InviteError("Invalid or expired invite link")
    normalized_email = invite.email.strip().lower()
    return InvitePreview(
        email=normalized_email,
        organization_id=invite.organization_id,
        organization_name=org.name,
        role=invite.role,
        account_exists=get_user_by_email(session, email=normalized_email) is not None,
    )


def activate_invite(
    session: Session,
    *,
    token: str,
    password: str,
) -> tuple[User, OrganizationInvite]:
    """Create a platform account from the invite email and join the organization."""
    invite = find_pending_invite_by_token(session, token=token)
    if invite is None:
        raise InviteError("Invalid or expired invite link")

    normalized_email = invite.email.strip().lower()
    existing_user = get_user_by_email(session, email=normalized_email)
    if existing_user is not None:
        raise InviteError("An account already exists for this email. Sign in to accept the invite.")

    user = create_user(
        session,
        email=normalized_email,
        password_hash=hash_password(password),
        role=PlatformRole.MEMBER.value,
    )
    if not get_membership(session, organization_id=invite.organization_id, user_id=user.id):
        add_organization_member(
            session,
            organization_id=invite.organization_id,
            user_id=user.id,
            role=invite.role,
        )
    mark_invite_accepted(session, invite)
    return user, invite


def accept_invite(session: Session, *, token: str, user: User) -> OrganizationInvite:
    """Redeem invite: create membership if the signed-in email matches."""
    invite = find_pending_invite_by_token(session, token=token)
    if invite is None:
        raise InviteError("Invalid or expired invite link")
    if user.email.strip().lower() != invite.email.strip().lower():
        raise InviteError("Sign in with the email address that received the invite")

    membership = get_membership(session, organization_id=invite.organization_id, user_id=user.id)
    if membership is not None:
        if is_active_member(membership):
            mark_invite_accepted(session, invite)
            return invite
        # Re-activate a previously deactivated member.
        membership.deactivated_at = None
        membership.deactivated_by_user_id = None
        membership.role = invite.role
        session.flush()
        mark_invite_accepted(session, invite)
        return invite

    add_organization_member(
        session,
        organization_id=invite.organization_id,
        user_id=user.id,
        role=invite.role,
    )
    mark_invite_accepted(session, invite)
    return invite
