"""Parse billing period dates from LLM JSON (ISO strings) for ``generic-bill-v1``."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

# Common utility-bill month labels the LLM may return.
_MONTH_NAME_TO_NUM = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def parse_bill_period_date(value: Any) -> date | None:
    """Coerce LLM output to ``date``; return ``None`` when unparseable."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    if not s:
        return None
    # ISO date or datetime prefix
    iso = s[:10] if len(s) >= 10 and s[4] == "-" else s
    try:
        return date.fromisoformat(iso)
    except ValueError:
        pass
    # MM/DD/YYYY or M/D/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(year, month, day)
    # "January 2025" / "Jan 2025" → first day of that month.
    m = re.match(r"^([A-Za-z]+)\s+(\d{4})$", s)
    if m:
        mon = _MONTH_NAME_TO_NUM.get(m.group(1).lower())
        if mon:
            return date(int(m.group(2)), mon, 1)
    return None
