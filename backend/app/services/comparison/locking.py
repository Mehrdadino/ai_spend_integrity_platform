"""Transaction-scoped locks for §3d anomaly persistence.

Site-level unique indexes on ``anomalies`` omit ``bill_id`` and ``rule_pack_version``;
concurrent §3e backfills for the same site can otherwise double-insert the same fingerprint.
"""

from __future__ import annotations

import uuid
import zlib

from sqlalchemy import text
from sqlalchemy.orm import Session


def _site_advisory_lock_key(site_id: uuid.UUID) -> int:
    """Map a site UUID to a 31-bit ``pg_advisory_xact_lock`` key (stable per site)."""
    return zlib.crc32(site_id.bytes) & 0x7FFFFFFF


def acquire_site_comparison_lock(session: Session, *, site_id: uuid.UUID) -> None:
    """Block until this transaction holds the per-site comparison lock.

    Released automatically at ``commit`` / ``rollback``. Call before §3d replace when
    ``site_id`` is set so parallel RQ backfill jobs serialize writes for that site.
    """
    session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": _site_advisory_lock_key(site_id)},
    )
