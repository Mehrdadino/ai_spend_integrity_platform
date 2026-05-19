"""Password policy validation (no database)."""

from __future__ import annotations

import unittest

from app.services.auth.password_policy import password_validation_errors


class TestPasswordPolicy(unittest.TestCase):
    def test_accepts_strong_password(self) -> None:
        self.assertEqual(password_validation_errors("Str0ng!Pass"), [])

    def test_rejects_short_password(self) -> None:
        issues = password_validation_errors("Ab1!")
        self.assertTrue(any("8 characters" in i for i in issues))

    def test_rejects_missing_uppercase(self) -> None:
        issues = password_validation_errors("str0ng!pass")
        self.assertTrue(any("uppercase" in i for i in issues))

    def test_rejects_disallowed_character(self) -> None:
        issues = password_validation_errors("Str0ng Pass!")
        self.assertTrue(any("only letters" in i for i in issues))


if __name__ == "__main__":
    unittest.main()
