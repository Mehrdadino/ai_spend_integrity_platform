"""OpenAI-compatible Chat Completions → ``generic-bill-v1`` JSON (optional worker path).

When ``Settings.extraction_llm_api_key`` is set, the worker asks for structured JSON
matching ``GenericBillExtractionPayload``. Uses stdlib **urllib** only (no extra
HTTP dependency). If the HTTP call or JSON parse fails, ``raw_extraction`` falls
back to a deterministic payload.

Bill **text** comes from ``document_text`` (``pypdf`` embedded layer) when available;
OCR is not invoked here.
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
from app.services.document_text import truncate_text_for_llm

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a billing-data extraction assistant. Reply with a single JSON object only, "
    "no markdown fences, matching the user's schema. Extract line items, amounts, currency, "
    "issuer, and spend hints from the bill text when provided. If bill text is missing or "
    "unreadable, return an empty lines array and conservative spend_domain hints."
)


def _message_from_error_object(err: object) -> str | None:
    """Extract a human message from a provider error object (dict, str, or list)."""
    if isinstance(err, str) and err.strip():
        return err.strip()
    if isinstance(err, list):
        for item in err:
            msg = _message_from_error_object(item)
            if msg:
                return msg
        return None
    if isinstance(err, dict):
        for key in ("message", "detail", "status"):
            msg = err.get(key)
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
            if isinstance(msg, list):
                nested = _message_from_error_object(msg)
                if nested:
                    return nested
    return None


def _http_error_detail(status_code: int, body: str) -> str:
    """Pull provider message from OpenAI/Gemini error JSON when present."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        snippet = body.strip()[:240]
        return f"LLM HTTP {status_code}" + (f": {snippet}" if snippet else "")

    candidates: list[object] = []
    if isinstance(data, dict):
        candidates.append(data)
    elif isinstance(data, list):
        candidates.extend(item for item in data if isinstance(item, dict))

    for item in candidates:
        err = item.get("error") if isinstance(item, dict) else None
        msg = _message_from_error_object(err) if err is not None else None
        if msg:
            return f"LLM HTTP {status_code}: {msg}"
        if isinstance(item, dict):
            top = _message_from_error_object(item)
            if top:
                return f"LLM HTTP {status_code}: {top}"

    return f"LLM HTTP {status_code}"


def _coerce_top_level_object(raw: Any, *, label: str) -> dict[str, Any]:
    """Accept dict or single-element list wrappers from some OpenAI-compatible gateways."""
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                return item
        raise RuntimeError(f"LLM {label} is a list without an object")
    if not isinstance(raw, dict):
        raise RuntimeError(f"LLM {label} must be a JSON object, got {type(raw).__name__}")
    return raw


def _first_choice_dict(raw_resp: dict[str, Any]) -> dict[str, Any]:
    """Return the first choice/candidate object from an OpenAI- or Gemini-shaped body."""
    choices = raw_resp.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            return choice
        if isinstance(choice, list):
            for item in choice:
                if isinstance(item, dict):
                    return item
    candidates = raw_resp.get("candidates")
    if isinstance(candidates, list) and candidates:
        cand = candidates[0]
        if isinstance(cand, dict):
            return cand
    raise RuntimeError("LLM response missing choices[0] or candidates[0]")


def _join_content_parts(parts: object) -> str:
    """Flatten multipart assistant content (OpenAI list, Gemini parts, nested lists)."""
    if isinstance(parts, str):
        return parts.strip()
    if isinstance(parts, list):
        chunks = [_text_from_content_part(item) for item in parts]
        return "\n".join(chunk for chunk in chunks if chunk.strip())
    if isinstance(parts, dict):
        return _text_from_content_part(parts)
    return ""


def _text_from_content_part(part: object) -> str:
    """Coerce one assistant ``content`` element (OpenAI / Gemini shapes) to text."""
    if isinstance(part, str):
        return part
    if isinstance(part, list):
        nested = [_text_from_content_part(item) for item in part]
        return "\n".join(chunk for chunk in nested if chunk.strip())
    if isinstance(part, dict):
        for key in ("text", "content", "output_text"):
            value = part.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, list):
                nested = [_text_from_content_part(item) for item in value]
                return "\n".join(chunk for chunk in nested if chunk.strip())
    return ""


def _extract_assistant_text(raw: Any) -> str:
    """Read assistant text from OpenAI ``choices`` or Gemini ``candidates`` response bodies."""
    raw_resp = _coerce_top_level_object(raw, label="HTTP body")
    choice = _first_choice_dict(raw_resp)

    message = choice.get("message")
    if message is None:
        # Gemini often uses candidates[].content.parts instead of message.content.
        gemini_content = choice.get("content")
        if isinstance(gemini_content, dict):
            parts = gemini_content.get("parts")
            joined = _join_content_parts(parts)
            if joined:
                return joined
        joined = _join_content_parts(choice.get("content"))
        if joined:
            return joined
        raise RuntimeError("LLM response missing message.content")

    if isinstance(message, str):
        return message

    if isinstance(message, list):
        joined = _join_content_parts(message)
        if joined:
            return joined
        raise RuntimeError("LLM message list had no extractable text")

    if not isinstance(message, dict):
        raise RuntimeError(f"LLM message has unsupported type: {type(message).__name__}")

    content = message.get("content")
    if content is None:
        raise RuntimeError("LLM response missing message.content")

    joined = _join_content_parts(content)
    if joined:
        return joined
    raise RuntimeError(f"LLM message content has unsupported type: {type(content).__name__}")


def _normalize_llm_bill_dict(data: Any) -> dict[str, Any]:
    """Coerce common LLM JSON drift (root list, ``lines`` object) before Pydantic validation."""
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                data = item
                break
        else:
            raise RuntimeError("LLM JSON root is a list without an object")

    if not isinstance(data, dict):
        raise RuntimeError(f"LLM JSON root must be an object, got {type(data).__name__}")

    lines = data.get("lines")
    if lines is None:
        data["lines"] = []
    elif isinstance(lines, dict):
        items = lines.get("items")
        if isinstance(items, list):
            data["lines"] = [row for row in items if isinstance(row, dict)]
        else:
            data["lines"] = [row for row in lines.values() if isinstance(row, dict)]
    elif isinstance(lines, list):
        data["lines"] = [row for row in lines if isinstance(row, dict)]
    else:
        data["lines"] = []

    return data


def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers some models emit."""
    t = text.strip()
    m = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", t, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t


def llm_generic_bill_dict(
    *,
    document: Document,
    settings: Settings,
    document_text: str | None = None,
) -> dict[str, Any]:
    """POST to OpenAI-compatible ``/chat/completions``; return a dict (not yet validated).

    Raises on non-2xx or invalid JSON so callers can fall back to deterministic extraction.
    """
    key = (settings.extraction_llm_api_key or "").strip()
    if not key:
        raise RuntimeError("extraction_llm_api_key is empty")

    base = (settings.extraction_llm_base_url or "").strip().rstrip("/")
    url = f"{base}/chat/completions"
    model = (settings.extraction_llm_model or "gpt-4o-mini").strip()

    schema_hint = (
        "Return JSON with keys: document_id (string UUID), spend_domain (string or null), "
        "spend_kind (string or null), issuer_name (string or null), currency (3-letter string), "
        "period_start (ISO date YYYY-MM-DD or null), period_end (ISO date YYYY-MM-DD or null), "
        "lines (array of objects with raw_label, amount, currency, quantity, quantity_unit, "
        "service_hint — all optional except raw_label when a line is present).\n"
        "Extract period_start and period_end from the bill's service period / statement dates when visible.\n"
        "document_id must equal the UUID above."
    )
    user_parts = [
        f"Document UUID: {document.id}",
        f"MIME type: {document.mime_type}",
        schema_hint,
    ]
    if document_text and document_text.strip():
        bounded = truncate_text_for_llm(document_text.strip(), max_chars=settings.extraction_llm_max_document_chars)
        user_parts.append("--- BEGIN BILL TEXT ---")
        user_parts.append(bounded)
        user_parts.append("--- END BILL TEXT ---")
    else:
        user_parts.append("(No bill text was extracted from the file.)")

    user = "\n".join(user_parts)

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
        raise RuntimeError(_http_error_detail(e.code, err_body)) from e
    except Exception as exc:
        logger.warning("extraction_llm: request failed: %s", exc)
        raise

    content = _extract_assistant_text(raw_resp)
    data = _normalize_llm_bill_dict(json.loads(_strip_json_fences(content)))
    data["document_id"] = str(document.id)
    return data


def format_llm_error_for_ui(exc: BaseException, *, max_len: int = 500) -> str:
    """Short, user-visible message for ``bills.summary.structured_error``."""
    msg = str(exc).strip() or type(exc).__name__
    prefix = "LLM structuring failed: "
    budget = max(0, max_len - len(prefix))
    if len(msg) > budget:
        msg = msg[: budget - 3] + "..."
    return prefix + msg


def safe_llm_generic_bill_dict(
    *,
    document: Document,
    settings: Settings,
    document_text: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(payload, None)`` on success or ``(None, error_message)`` for bill summary UI."""
    try:
        return (
            llm_generic_bill_dict(
                document=document,
                settings=settings,
                document_text=document_text,
            ),
            None,
        )
    except Exception as exc:
        logger.exception("extraction_llm: failed for document_id=%s", document.id)
        return None, format_llm_error_for_ui(exc)
