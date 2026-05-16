"""P1 JWT helpers (no database)."""

from __future__ import annotations

import unittest
import uuid

from app.services.auth.jwt_tokens import create_access_token, decode_access_token


class TestAuthJwt(unittest.TestCase):
    def test_roundtrip_claims(self) -> None:
        user_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id,
            role="admin",
            email="admin@dev.local",
        )
        claims = decode_access_token(token)
        self.assertEqual(claims.user_id, user_id)
        self.assertEqual(claims.role, "admin")
        self.assertEqual(claims.email, "admin@dev.local")


if __name__ == "__main__":
    unittest.main()
