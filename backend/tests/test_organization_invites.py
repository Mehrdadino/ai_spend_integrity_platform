"""Organization invite preview and activation (B2B set-password flow)."""

from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.organization import Organization
from app.models.organization_invite import OrganizationInvite
from app.models.organization_member import OrganizationMember
from app.models.user import PlatformRole, User
from app.repositories.organization_invites import create_organization_invite
from app.repositories.users import create_user, get_user_by_email
from app.services.auth.passwords import hash_password, verify_password
from app.services.auth.secrets import generate_password_reset_token
from app.services.organization_invites import (
    InviteError,
    activate_invite,
    preview_invite,
)
from app.services.organization_team import build_team_roster


class OrganizationInviteActivationTests(unittest.TestCase):
    """SQLite in-memory checks for invite preview + activate."""

    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        # Only tables needed for invite activation (avoid JSONB models on SQLite).
        for table in (
            User.__table__,
            Organization.__table__,
            OrganizationInvite.__table__,
            OrganizationMember.__table__,
        ):
            table.create(self.engine, checkfirst=True)
        self.Session = sessionmaker(bind=self.engine)
        self.org_id = uuid.uuid4()
        self.inviter_id = uuid.uuid4()
        with self.Session() as session:
            session.add(
                Organization(
                    id=self.org_id,
                    name="Acme Utilities",
                    slug="acme-utilities",
                    created_by_user_id=self.inviter_id,
                )
            )
            session.add(
                User(
                    id=self.inviter_id,
                    email="admin@acme.com",
                    password_hash=hash_password("Admin-Pass1!"),
                    role=PlatformRole.MEMBER.value,
                )
            )
            session.commit()

    def _pending_invite(self, session: Session, *, email: str) -> str:
        token = generate_password_reset_token()
        create_organization_invite(
            session,
            organization_id=self.org_id,
            email=email,
            role="member",
            token_hash=hash_password(token),
            invited_by_user_id=self.inviter_id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        session.commit()
        return token

    def test_roster_shows_invite_then_active_member(self) -> None:
        with self.Session() as session:
            token = self._pending_invite(session, email="roster@acme.com")
            roster = build_team_roster(session, organization_id=self.org_id)
            self.assertEqual(len(roster), 1)
            self.assertEqual(roster[0].row_type, "invite")
            self.assertEqual(roster[0].status, "invite_sent")

            activate_invite(session, token=token, password="Roster-Pass1!")
            session.commit()

            roster2 = build_team_roster(session, organization_id=self.org_id)
            self.assertEqual(len(roster2), 1)
            self.assertEqual(roster2[0].row_type, "member")
            self.assertEqual(roster2[0].status, "active")

    def test_preview_new_user(self) -> None:
        token = ""
        with self.Session() as session:
            token = self._pending_invite(session, email="newuser@acme.com")
            preview = preview_invite(session, token=token)
            self.assertEqual(preview.email, "newuser@acme.com")
            self.assertEqual(preview.organization_name, "Acme Utilities")
            self.assertFalse(preview.account_exists)

    def test_activate_creates_user_and_membership(self) -> None:
        token = ""
        with self.Session() as session:
            token = self._pending_invite(session, email="joiner@acme.com")
            user, invite = activate_invite(session, token=token, password="Joiner-Pass1!")
            session.commit()

            self.assertEqual(user.email, "joiner@acme.com")
            self.assertIsNotNone(invite.accepted_at)
            loaded = get_user_by_email(session, email="joiner@acme.com")
            assert loaded is not None
            self.assertTrue(verify_password("Joiner-Pass1!", loaded.password_hash or ""))

        with self.Session() as session:
            with self.assertRaises(InviteError):
                preview_invite(session, token=token)

    def test_activate_rejects_existing_account(self) -> None:
        with self.Session() as session:
            create_user(
                session,
                email="existing@acme.com",
                password_hash=hash_password("Existing-Pass1!"),
            )
            token = self._pending_invite(session, email="existing@acme.com")
            session.commit()

        with self.Session() as session:
            with self.assertRaises(InviteError):
                activate_invite(session, token=token, password="Other-Pass1!")
            preview = preview_invite(session, token=token)
            self.assertTrue(preview.account_exists)


if __name__ == "__main__":
    unittest.main()
