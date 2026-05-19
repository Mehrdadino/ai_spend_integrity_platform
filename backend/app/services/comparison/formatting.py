"""Human-facing decimal formatting for comparison summaries and evidence strings.

Rule evaluation uses full ``Decimal`` precision from normalized bills (``Numeric(18, 4)`` in
Postgres). This module only shapes **display** copy — summaries, explainability evidence
strings, and UI-facing amounts — so reviewers see currency-style values (two decimals).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

_TWO_PLACES = Decimal("0.01")


def format_money(value: Decimal) -> str:
    """Format a currency amount with exactly two fractional digits."""
    return str(value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP))


def format_percent(value: Decimal) -> str:
    """Format a percentage magnitude with two fractional digits (no ``%`` suffix)."""
    return str(value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP))


def format_percent_from_float(value: float) -> str:
    """Format a float percentage (e.g. from JSON evidence) for display."""
    return format_percent(Decimal(str(value)))
