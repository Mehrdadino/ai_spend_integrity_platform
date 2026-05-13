"""Stable **string** codes for 2c normalization (not Postgres enums).

We deliberately keep these as Python constants so water, telecom, contract drift,
and other domains extend **mapping tables + docs**, not new DDL for every category.
"""

from __future__ import annotations

# Bumped when normalization rules materially change (stored on ``bills.normalization_version``).
NORM_VERSION = "norm-v1"

# --- Spend partitioning (``bills.spend_domain`` / ``spend_kind``) -----------------
SPEND_DOMAIN_UNSPECIFIED = "unspecified"
SPEND_DOMAIN_UTILITY = "utility"
SPEND_DOMAIN_TELECOM = "telecom"
SPEND_DOMAIN_CONTRACT = "contract"

# --- Generic line kinds (``bill_line_items.canonical_line_kind``) -----------------
# Comparable across energy / water / internet / contract invoices.
LINE_KIND_CHARGE = "charge"
LINE_KIND_CREDIT = "credit"
LINE_KIND_TAX = "tax"
LINE_KIND_FEE = "fee"
LINE_KIND_USAGE = "usage"
LINE_KIND_ADJUSTMENT = "adjustment"
LINE_KIND_OTHER = "other"

# --- Canonical quantity units (``bill_line_items.quantity_unit``) -----------------
UNIT_KWH = "kwh"
UNIT_MWH = "mwh"
UNIT_THERM = "therm"
UNIT_CCF = "ccf"
UNIT_LITER = "liter"
UNIT_GALLON = "gallon"
UNIT_MBPS = "mbps"
UNIT_GB = "gb"
UNIT_COUNT = "count"
UNIT_UNKNOWN = "unknown"
