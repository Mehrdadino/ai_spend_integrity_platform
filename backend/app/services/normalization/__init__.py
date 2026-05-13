"""2c normalization: map validated extraction payloads → canonical codes + units.

Dispatch by ``extraction_version``; persist via ``app.services.bill_sync`` (2d).
Domain-specific rules stay in small modules (``units``, ``line_kind``, ``from_stub``)
so new verticals add files or rows—not ORM churn.
"""

from app.services.normalization.from_extraction import build_normalized_bundle

__all__ = ["build_normalized_bundle"]
