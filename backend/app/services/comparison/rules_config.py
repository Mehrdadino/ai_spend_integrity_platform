"""Thresholds for §3b rule pack v1 (code-first; no LLM).

Tune here or override via env in a later pass; values are versioned with
``RULE_PACK_VERSION`` in ``rule_pack_v1``.
"""

from __future__ import annotations

from decimal import Decimal

RULE_PACK_VERSION = "comparison-v1"

# Month-over-month total (current vs immediate prior bill).
MOM_PERCENT_WARNING = Decimal("10")  # |delta %| >= 10 → warning
MOM_PERCENT_CRITICAL = Decimal("25")  # |delta %| >= 25 → critical
MOM_ABSOLUTE_WARNING = Decimal("50")  # |delta USD| >= 50 when % is undefined

# Header total vs sum(line amounts) on the current bill (data quality).
HEADER_LINES_TOLERANCE = Decimal("0.05")  # allow 5 cents rounding
