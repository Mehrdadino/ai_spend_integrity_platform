"""Parse ``BILL_SPEC_V1`` blocks embedded in PDF text for deterministic structuring.

Test and demo PDFs include a machine-readable spec block so ``raw_extraction`` can build
``generic-bill-v1`` JSON without an LLM when ``EXTRACTION_LLM_API_KEY`` is unset.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from uuid import UUID

from app.schemas.extraction.period_dates import parse_bill_period_date

_SPEC_START = "BILL_SPEC_V1"
_SPEC_END = "END_BILL_SPEC"

# ``line: label | amount [| qty=N | unit=kwh | kind=fee]``
_LINE_RE = re.compile(
    r"^line:\s*(?P<label>.+?)\s*\|\s*(?P<amount>-?\d+(?:\.\d+)?)"
    r"(?:\s*\|\s*(?P<extras>.*))?$",
    re.IGNORECASE,
)
_KV_RE = re.compile(r"^([a-z_]+):\s*(.+)$", re.IGNORECASE)


def pdf_text_contains_bill_spec(text: str) -> bool:
    """True when extracted PDF text includes a parseable spec block."""
    return _SPEC_START in text and _SPEC_END in text


def parse_generic_bill_dict_from_pdf_text(
    text: str,
    *,
    document_id: UUID,
) -> dict[str, Any] | None:
    """Return ``generic-bill-v1``-shaped dict from embedded spec, or ``None`` if absent/invalid."""
    if not pdf_text_contains_bill_spec(text):
        return None
    start = text.index(_SPEC_START)
    end = text.index(_SPEC_END, start)
    block = text[start:end]
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]

    meta: dict[str, str] = {}
    bill_lines: list[dict[str, Any]] = []

    for raw in lines:
        if raw.upper() == _SPEC_START:
            continue
        m_line = _LINE_RE.match(raw)
        if m_line:
            label = m_line.group("label").strip()
            amount = float(m_line.group("amount"))
            extras = (m_line.group("extras") or "").strip()
            entry: dict[str, Any] = {
                "raw_label": label,
                "amount": amount,
                "currency": "USD",
            }
            if extras:
                for part in extras.split("|"):
                    part = part.strip()
                    if part.lower().startswith("qty="):
                        entry["quantity"] = float(part[4:].strip())
                    elif part.lower().startswith("unit="):
                        entry["quantity_unit"] = part[5:].strip()
                    elif part.lower().startswith("kind="):
                        hint = part[5:].strip().lower()
                        if hint == "fee":
                            entry["service_hint"] = "fee"
                        elif hint == "electric":
                            entry["service_hint"] = "electric"
            if "surcharge" in label.lower() or "fee" in label.lower():
                entry.setdefault("service_hint", "fee")
            if "kwh" in label.lower() or entry.get("quantity_unit") == "kwh":
                entry.setdefault("service_hint", "electric")
                entry.setdefault("quantity_unit", entry.get("quantity_unit") or "kwh")
            bill_lines.append(entry)
            continue

        m_kv = _KV_RE.match(raw)
        if not m_kv:
            continue
        key = m_kv.group(1).strip().lower()
        val = m_kv.group(2).strip()
        # ``header_total`` in spec is for human PDF display only; bill total is sum of lines.
        if key != "header_total":
            meta[key] = val

    period_start = _parse_meta_date(meta.get("period_start"))
    period_end = _parse_meta_date(meta.get("period_end"))

    out: dict[str, Any] = {
        "document_id": str(document_id),
        "spend_domain": meta.get("spend_domain") or "utility",
        "spend_kind": meta.get("spend_kind") or "electricity",
        "issuer_name": meta.get("issuer_name"),
        "currency": (meta.get("currency") or "USD").upper()[:3],
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "lines": bill_lines,
    }
    return out


def _parse_meta_date(raw: str | None) -> date | None:
    if not raw:
        return None
    return parse_bill_period_date(raw)
