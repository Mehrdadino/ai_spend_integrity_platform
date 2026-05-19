"""Rate limit counter logic (mocked Redis)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.services.rate_limit import RateLimitExceeded, check_rate_limit


class TestRateLimit(unittest.TestCase):
    @patch("app.services.rate_limit._get_redis")
    @patch("app.services.rate_limit.get_settings")
    def test_allows_under_limit(self, mock_settings: MagicMock, mock_redis: MagicMock) -> None:
        mock_settings.return_value.rate_limit_enabled = True
        mock_settings.return_value.app_env = "development"
        r = MagicMock()
        r.incr.return_value = 1
        mock_redis.return_value = r
        check_rate_limit(key="test", limit=5, window_seconds=60)
        r.expire.assert_called_once()

    @patch("app.services.rate_limit._get_redis")
    @patch("app.services.rate_limit.get_settings")
    def test_blocks_over_limit(self, mock_settings: MagicMock, mock_redis: MagicMock) -> None:
        mock_settings.return_value.rate_limit_enabled = True
        mock_settings.return_value.app_env = "development"
        r = MagicMock()
        r.incr.return_value = 6
        r.ttl.return_value = 42
        mock_redis.return_value = r
        with self.assertRaises(RateLimitExceeded) as ctx:
            check_rate_limit(key="test", limit=5, window_seconds=60)
        self.assertEqual(ctx.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
