"""RegisterRequest validates email shape."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.auth import RegisterRequest


class TestRegisterSchema(unittest.TestCase):
    def test_accepts_work_email(self) -> None:
        body = RegisterRequest(email="user@acme.com", password="Secure-Pass1!")
        self.assertEqual(str(body.email), "user@acme.com")

    def test_rejects_short_password(self) -> None:
        with self.assertRaises(ValidationError):
            RegisterRequest(email="user@acme.com", password="short")


if __name__ == "__main__":
    unittest.main()
