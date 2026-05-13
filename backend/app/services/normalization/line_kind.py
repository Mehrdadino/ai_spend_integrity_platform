"""Heuristic **generic** line classification from free-text labels (2c).

Energy-specific wording still maps into shared ``LINE_KIND_*`` codes so water or
telecom lines can reuse comparison and UX buckets later.
"""

from __future__ import annotations

from app.constants.normalization import (
    LINE_KIND_ADJUSTMENT,
    LINE_KIND_CHARGE,
    LINE_KIND_CREDIT,
    LINE_KIND_FEE,
    LINE_KIND_OTHER,
    LINE_KIND_TAX,
    LINE_KIND_USAGE,
)


def infer_line_kind(*, raw_label: str, has_quantity: bool) -> str:
    """Return a ``LINE_KIND_*`` string from ``raw_label`` (case-insensitive).

    ``has_quantity`` nudges ambiguous rows toward ``LINE_KIND_USAGE`` (metered).
    """
    t = raw_label.strip().lower()
    if not t:
        return LINE_KIND_OTHER

    if "credit" in t or "cr " in t or t.startswith("cr ") or " refund" in t:
        return LINE_KIND_CREDIT
    if "tax" in t or "vat" in t or "gst" in t or "hst" in t:
        return LINE_KIND_TAX
    if "fee" in t or "surcharge" in t or "rider" in t:
        return LINE_KIND_FEE
    if "adjust" in t or "correction" in t or "true-up" in t or "true up" in t:
        return LINE_KIND_ADJUSTMENT

    if has_quantity and any(
        x in t
        for x in (
            "kwh",
            "kw ",
            "therm",
            "ccf",
            "gallon",
            "gal ",
            " liter",
            "litre",
            " cubic",
            "usage",
            "consumption",
            "meter",
        )
    ):
        return LINE_KIND_USAGE

    if "charge" in t or "delivery" in t or "supply" in t or "service" in t or "amount" in t:
        return LINE_KIND_CHARGE

    return LINE_KIND_OTHER
