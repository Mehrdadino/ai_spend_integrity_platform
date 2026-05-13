"""Map noisy unit strings (LLM or OCR) to canonical ``quantity_unit`` codes (2c).

Only a small starter set is recognized; unknown inputs return ``UNIT_UNKNOWN``.
Expand alias tables as new bill types land (water gal/L, contract seat-count, …).
"""

from __future__ import annotations

from app.constants.normalization import (
    UNIT_CCF,
    UNIT_COUNT,
    UNIT_GALLON,
    UNIT_GB,
    UNIT_KWH,
    UNIT_LITER,
    UNIT_MBPS,
    UNIT_MWH,
    UNIT_THERM,
    UNIT_UNKNOWN,
)


def canonicalize_quantity_unit(raw: str | None) -> str | None:
    """Return a canonical unit code, or ``None`` if ``raw`` is empty.

    Matching is ASCII-lowercased and strips whitespace / common punctuation.
    """
    if raw is None:
        return None
    s = raw.strip().lower().replace(".", "").replace("³", "3")
    if not s:
        return None

    # Energy / volume (utility)
    if s in ("kwh", "kw-hr", "kwhr", "kilowatt-hour", "kilowatt-hours", "kilowatt hour"):
        return UNIT_KWH
    if s in ("mwh", "megawatt-hour", "megawatt-hours"):
        return UNIT_MWH
    if s in ("therm", "therms", "th"):
        return UNIT_THERM
    if s in ("ccf", "100 cubic feet", "100cf"):
        return UNIT_CCF
    if s in ("gal", "gallon", "gallons"):
        return UNIT_GALLON
    if s in ("l", "liter", "litre", "liters", "litres"):
        return UNIT_LITER

    # Telecom-ish (extend for MHz, SMS bundles, etc.)
    if s in ("mbps", "mb/s", "megabits per second", "megabit per second"):
        return UNIT_MBPS
    if s in ("gb", "gigabyte", "gigabytes"):
        return UNIT_GB

    if s in ("ea", "each", "qty", "quantity", "count", "units"):
        return UNIT_COUNT

    return UNIT_UNKNOWN
