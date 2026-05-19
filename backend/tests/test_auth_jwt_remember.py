"""JWT expiry reflects remember-device vs session lifetime."""

from __future__ import annotations

import unittest
import uuid
import jwt

from app.config import get_settings
from app.services.auth.jwt_tokens import create_access_token, decode_access_token


class TestAuthJwtRemember(unittest.TestCase):
    def test_remember_extends_expiry(self) -> None:
        settings = get_settings()
        user_id = uuid.uuid4()
        session_token = create_access_token(
            user_id=user_id,
            role="member",
            email="a@b.com",
            remember_device=False,
        )
        remember_token = create_access_token(
            user_id=user_id,
            role="member",
            email="a@b.com",
            remember_device=True,
        )
        session_payload = jwt.decode(
            session_token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        remember_payload = jwt.decode(
            remember_token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        session_ttl = session_payload["exp"] - session_payload["iat"]
        remember_ttl = remember_payload["exp"] - remember_payload["iat"]
        self.assertGreater(remember_ttl, session_ttl)
        self.assertTrue(remember_payload.get("rem"))
        self.assertFalse(session_payload.get("rem"))

    def test_decode_still_works(self) -> None:
        user_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id,
            role="admin",
            email="admin@dev.local",
            remember_device=True,
        )
        claims = decode_access_token(token)
        self.assertEqual(claims.user_id, user_id)


if __name__ == "__main__":
    unittest.main()
