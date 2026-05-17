"""Normalize optional document display names (blank → NULL in Postgres)."""

from __future__ import annotations

from typing import Optional


def normalize_display_name(value: Optional[str]) -> Optional[str]:
    """Strip whitespace; empty string becomes ``None`` so the name can be cleared."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None
