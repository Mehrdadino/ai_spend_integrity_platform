"""LoginRequest accepts dev-style emails (e.g. admin@dev.local)."""

from __future__ import annotations

import unittest

from app.schemas.auth import LoginRequest


class TestAuthLoginSchema(unittest.TestCase):
    def test_dev_local_email_allowed(self) -> None:
        body = LoginRequest(email="admin@dev.local", password="dev-admin-change-me")
        self.assertEqual(body.email, "admin@dev.local")


if __name__ == "__main__":
    unittest.main()
