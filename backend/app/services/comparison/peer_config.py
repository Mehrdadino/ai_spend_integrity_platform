"""Thresholds and version string for §3c cross-site peer rule pack.

Values are code-first (no LLM). Tune here; version bumps with rule changes.
"""

from __future__ import annotations

from decimal import Decimal

# Separate from §3b ``comparison-v1.*`` so inbox can filter site vs peer signals.
PEER_RULE_PACK_VERSION = "comparison-peer-v1"

# Peer set must include bills from at least this many *other* sites (pilot-tunable).
MIN_PEER_SITES = 3

# Max peer bills loaded per anchor evaluation (SQL + in-memory slice filter).
MAX_PEER_BILLS = 50
MAX_PEER_CANDIDATES = 200

# Billing period window: anchor month ± slack days on ``effective_period_end``.
PERIOD_WINDOW_SLACK_DAYS = 5

# ``peer_fee_line_widespread``: fee fingerprint on anchor and on ≥ this share of peers.
PEER_FEE_WIDESPREAD_PCT = Decimal("80")

# ``peer_fee_line_rare``: ≤ this many peer bills share the fee fingerprint.
PEER_FEE_RARE_MAX_PEER_MATCHES = 1

# ``peer_usage_or_total_outlier``: anchor above peer p75 × factor or 2× median.
PEER_OUTLIER_P75_FACTOR = Decimal("1.25")
PEER_OUTLIER_MEDIAN_FACTOR = Decimal("2")

# Domains eligible for automatic peer discovery in v1.
PEER_SUPPORTED_SPEND_DOMAINS = frozenset({"utility", "telecom"})
