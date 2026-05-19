"""OTP and reset token generators (no database)."""

from __future__ import annotations

import re
import unittest

from app.services.auth.secrets import generate_login_otp, generate_password_reset_token


class TestAuthSecrets(unittest.TestCase):
    def test_login_otp_is_six_digits(self) -> None:
        code = generate_login_otp()
        self.assertRegex(code, r"^\d{6}$")

    def test_reset_token_is_url_safe(self) -> None:
        token = generate_password_reset_token()
        self.assertGreater(len(token), 20)
        self.assertIsNone(re.search(r"[^\w\-]", token))


if __name__ == "__main__":
    unittest.main()
