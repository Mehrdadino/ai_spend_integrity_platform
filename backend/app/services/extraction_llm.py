"""OpenAI-compatible Chat Completions → ``generic-bill-v1`` JSON (optional worker path).

When ``Settings.extraction_llm_api_key`` is set, the worker asks for structured JSON
matching ``GenericBillExtractionPayload``. Uses stdlib **urllib** only (no extra
HTTP dependency). If the HTTP call or JSON parse fails, ``raw_extraction`` falls
back to a deterministic payload.

Tenancy: the model never receives cross-tenant identifiers beyond ``document_id``
and MIME type; expand with redacted OCR text when available.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any

from app.config import Settings
from app.models.document import Document

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a billing-data extraction assistant. Reply with a single JSON object only, "
    "no markdown fences, matching the user's schema. If you lack bill text, return "
    "an empty lines array and conservative spend_domain hints (e.g. unspecified)."
)


def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers some models emit."""
    t = text.strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", t, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t


def llm_generic_bill_dict(*, document: Document, settings: Settings) -> dict[str, Any]:
    """POST to OpenAI-compatible ``/chat/completions``; return a dict (not yet validated).

    Raises on non-2xx or invalid JSON so callers can fall back to deterministic extraction.
    """
    key = (settings.extraction_llm_api_key or "").strip()
    if not key:
        raise RuntimeError("extraction_llm_api_key is empty")

    base = (settings.extraction_llm_base_url or "").strip().rstrip("/")
    url = f"{base}/chat/completions"
    model = (settings.extraction_llm_model or "gpt-4o-mini").strip()

    user = (
        f"Document UUID: {document.id}\n"
        f"MIME type: {document.mime_type}\n"
        "Return JSON with keys: document_id (string UUID), spend_domain (string or null), "
        "spend_kind (string or null), issuer_name (string or null), currency (3-letter string), "
        "lines (array of objects with raw_label, amount, currency, quantity, quantity_unit, "
        "service_hint — all optional except raw_label when a line is present).\n"
        "document_id must equal the UUID above."
    )

    body = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
    }
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    timeout = max(5, int(settings.extraction_llm_timeout_seconds))

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_resp = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:2000]
        logger.warning("extraction_llm: HTTP %s %s", e.code, err_body)
        raise RuntimeError(f"LLM HTTP {e.code}") from e
    except Exception as exc:
        logger.warning("extraction_llm: request failed: %s", exc)
        raise

    try:
        content = raw_resp["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("LLM response missing choices[0].message.content") from exc

    if not isinstance(content, str):
        raise RuntimeError("LLM message content is not a string")

    data = json.loads(_strip_json_fences(content))
    if not isinstance(data, dict):
        raise RuntimeError("LLM JSON root must be an object")

    # Hard-bind tenant document to avoid cross-document writes if the model drifts.
    data["document_id"] = str(document.id)
    return data


def safe_llm_generic_bill_dict(*, document: Document, settings: Settings) -> dict[str, Any] | None:
    """Return LLM dict or ``None`` on any failure (caller supplies fallback)."""
    try:
        return llm_generic_bill_dict(document=document, settings=settings)
    except Exception:
        logger.exception("extraction_llm: failed for document_id=%s", document.id)
        return None