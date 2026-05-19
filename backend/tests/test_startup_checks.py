"""Production configuration guardrails."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.startup_checks import validate_settings_for_runtime


class TestStartupChecks(unittest.TestCase):
    @patch("app.startup_checks.get_settings")
    def test_production_rejects_weak_jwt(self, mock_settings: MagicMock) -> None:
        mock_settings.return_value.app_env = "production"
        mock_settings.return_value.redis_url = "redis://localhost/0"
        mock_settings.return_value.jwt_secret_key = "change-me-in-production"
        mock_settings.return_value.auth_allow_dev_org_header = False
        mock_settings.return_value.rate_limit_enabled = True
        mock_settings.return_value.auth_allow_registration = False
        with self.assertRaises(RuntimeError):
            validate_settings_for_runtime()


if __name__ == "__main__":
    unittest.main()
