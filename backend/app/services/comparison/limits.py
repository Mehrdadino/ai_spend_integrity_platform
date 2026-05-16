"""Shared caps for §3a prior-bill scans and §3e backfill (single source of truth).

``list_bills_for_site`` and RQ backfill import these constants so API defaults, worker jobs,
and repository clamps stay aligned when we raise site history limits.
"""

from __future__ import annotations

# Default rows loaded per site when ordering bills (newest first) for backfill chains.
DEFAULT_SITE_BILL_SCAN = 500

# Hard ceiling for explicit ``limit`` arguments on API/query params (single request).
MAX_SITE_BILL_SCAN = 2000

# §3e site-wide refresh walks history in keyset pages; 0 in settings means no cap.
DEFAULT_SITE_REFRESH_MAX_BILLS = 10_000
