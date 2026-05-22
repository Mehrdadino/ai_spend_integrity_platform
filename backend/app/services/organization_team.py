"""Organization team roster: members + open invites with display status."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

from sqlalchemy.orm import Session

from app.models.organization_invite import OrganizationInvite
from app.models.organization_member import OrganizationMember
from app.repositories.organization_invites import list_open_invites_for_organization
from app.repositories.organization_members import list_members_for_organization
from app.repositories.users import get_user_by_email

RowType = Literal["member", "invite"]


@dataclass(frozen=True)
class TeamRosterRow:
    """One row in the org team directory (member or outstanding invite)."""

    row_type: RowType
    email: str
    role: str
    status: str
    status_label: str
    user_id: Optional[uuid.UUID]
    invite_id: Optional[uuid.UUID]
    joined_at: Optional[datetime]
    invited_at: Optional[datetime]
    expires_at: Optional[datetime]
    deactivated_at: Optional[datetime] = None
    deactivated_by_email: Optional[str] = None


def _as_utc(dt: datetime) -> datetime:
    """Normalize datetimes for comparison (SQLite tests may return naive UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _invite_status_label(
    invite: OrganizationInvite,
    *,
    account_exists: bool,
    now: datetime,
) -> tuple[str, str]:
    """Machine status + human label for a non-accepted invite."""
    if _as_utc(invite.expires_at) <= now:
        return "expired", "Invite expired"
    if account_exists:
        return (
            "awaiting_sign_in",
            "Account created — sign in to join",
        )
    return (
        "invite_sent",
        "Invite sent — awaiting password setup",
    )


def build_team_roster(session: Session, *, organization_id: uuid.UUID) -> list[TeamRosterRow]:
    """Members (active) plus unaccepted invites (pending or expired) for the directory UI."""
    now = datetime.now(timezone.utc)
    rows: list[TeamRosterRow] = []

    for member in list_members_for_organization(session, organization_id=organization_id):
        rows.append(_member_row(member))

    # Only active members block duplicate invite rows for the same email.
    member_emails = {r.email for r in rows if r.status != "deactivated"}
    for invite in list_open_invites_for_organization(session, organization_id=organization_id):
        normalized = invite.email.strip().lower()
        if normalized in member_emails:
            continue
        rows.append(_invite_row(session, invite=invite, now=now))

    rows.sort(key=lambda r: (0 if r.row_type == "member" else 1, r.email))
    return rows


def _member_row(member: OrganizationMember) -> TeamRosterRow:
    if member.deactivated_at is not None:
        deactivated_by = member.deactivated_by
        return TeamRosterRow(
            row_type="member",
            email=member.user.email,
            role=member.role,
            status="deactivated",
            status_label="Deactivated",
            user_id=member.user_id,
            invite_id=None,
            joined_at=member.created_at,
            invited_at=None,
            expires_at=None,
            deactivated_at=member.deactivated_at,
            deactivated_by_email=deactivated_by.email if deactivated_by else None,
        )
    return TeamRosterRow(
        row_type="member",
        email=member.user.email,
        role=member.role,
        status="active",
        status_label="Active member",
        user_id=member.user_id,
        invite_id=None,
        joined_at=member.created_at,
        invited_at=None,
        expires_at=None,
    )


def _invite_row(
    session: Session,
    *,
    invite: OrganizationInvite,
    now: datetime,
) -> TeamRosterRow:
    account_exists = get_user_by_email(session, email=invite.email) is not None
    status, status_label = _invite_status_label(invite, account_exists=account_exists, now=now)
    return TeamRosterRow(
        row_type="invite",
        email=invite.email,
        role=invite.role,
        status=status,
        status_label=status_label,
        user_id=None,
        invite_id=invite.id,
        joined_at=None,
        invited_at=invite.created_at,
        expires_at=invite.expires_at,
    )
