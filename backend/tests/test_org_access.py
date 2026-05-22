"""Per-org membership access rules (no Postgres)."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import MagicMock, patch

from app.models.organization import Organization
from app.models.organization_member import OrgMemberRole
from app.models.user import PlatformRole, User
from app.services.auth.access import (
    user_can_access_organization,
    user_can_manage_organization,
    user_can_write_organization,
)


class TestOrgAccess(unittest.TestCase):
    def _user(self, role: str = PlatformRole.MEMBER.value) -> User:
        return User(id=uuid.uuid4(), email="u@acme.com", role=role, password_hash="x")

    def _org(self) -> Organization:
        return Organization(id=uuid.uuid4(), name="Acme", slug="acme", created_by_user_id=uuid.uuid4())

    @patch("app.services.auth.access.get_active_membership")
    def test_member_can_access(self, get_active_membership: MagicMock) -> None:
        session = MagicMock()
        user = self._user()
        org = self._org()
        get_active_membership.return_value = MagicMock(role=OrgMemberRole.MEMBER.value)
        self.assertTrue(user_can_access_organization(session, user, org))

    @patch("app.services.auth.access.get_active_membership")
    def test_viewer_cannot_write(self, get_active_membership: MagicMock) -> None:
        session = MagicMock()
        user = self._user()
        org = self._org()
        get_active_membership.return_value = MagicMock(role=OrgMemberRole.VIEWER.value)
        self.assertFalse(user_can_write_organization(session, user, org))

    @patch("app.services.auth.access.get_active_membership")
    def test_org_admin_can_manage(self, get_active_membership: MagicMock) -> None:
        session = MagicMock()
        user = self._user()
        org = self._org()
        get_active_membership.return_value = MagicMock(role=OrgMemberRole.ORG_ADMIN.value)
        self.assertTrue(user_can_manage_organization(session, user, org))


if __name__ == "__main__":
    unittest.main()
