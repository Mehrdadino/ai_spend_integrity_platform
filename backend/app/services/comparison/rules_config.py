"""Thresholds for §3b rule pack v1 (code-first; no LLM).

Tune here or override via env in a later pass; values are versioned with
``RULE_PACK_VERSION`` in ``rule_pack_v1``.
"""

from __future__ import annotations

from decimal import Decimal

RULE_PACK_VERSION = "comparison-v1.2"

# Month-over-month total (current vs immediate prior bill).
MOM_PERCENT_WARNING = Decimal("10")  # |delta %| >= 10 → warning
MOM_PERCENT_CRITICAL = Decimal("25")  # |delta %| >= 25 → critical
MOM_ABSOLUTE_WARNING = Decimal("50")  # |delta USD| >= 50 when % is undefined

# Header total vs sum(line amounts) on the current bill (data quality).
HEADER_LINES_TOLERANCE = Decimal("0.05")  # allow 5 cents rounding

# Single-bill integrity (no prior required).
FEES_SHARE_WARNING_PCT = Decimal("15")  # fee sum >= 15% of bill total → warning
FEES_SHARE_MIN_TOTAL = Decimal("25")  # ignore tiny totals
PENALTY_FEE_LABEL_PATTERN = (
    r"late\s*(payment|fee)?|reconnect|disconnect|penalty|collection\s*fee|"
    r"returned\s*check|insufficient\s*funds|nsf"
)

# Tax share of bill total (single-bill; complements fee share).
TAX_SHARE_WARNING_PCT = Decimal("8")  # tax sum >= 8% of bill total → warning
TAX_SHARE_MIN_TOTAL = Decimal("25")  # ignore tiny totals (same floor as fees)

# Extraction quality: few structured lines on a text-rich PDF.
EXTRACTION_MIN_LINE_COUNT = 2
