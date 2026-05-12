"""Inbound provider webhook helpers: verify signatures, parse MIME, pick bill files.

Step **1e**: HTTP multipart (SendGrid Inbound Parse, Mailgun routes, similar) → bytes
in object storage + ``documents`` row, same shape as CLI upload.

Step **1f**: tenant from ``Organization.ingest_email_token`` URL segment; optional
``site`` hint parsed from ``To`` / envelope text (``site.<uuid>`` substring).

Step **1g**: attachment policy — PDF (or octet-stream + ``.pdf`` name), size cap from
``Settings.max_upload_bytes``, max count from ``Settings.inbound_email_max_documents_per_request``.
"""

from __future__ import annotations

import email.policy
import hashlib
import hmac
import json
import logging
import re
from email import message_from_bytes
from email.message import Message
from typing import Any, Optional
from uuid import UUID

from starlette.datastructures import FormData, Headers, UploadFile

from app.config import Settings

logger = logging.getLogger(__name__)

# Optional site hint inside the recipient local-part, e.g. ``bills+site.{uuid}@...``.
_SITE_UUID_IN_TEXT = re.compile(
    r"site[._](?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
    re.IGNORECASE,
)
_SENDGRID_ATTACHMENT_KEY = re.compile(r"^attachment\d+$", re.IGNORECASE)


def verify_mailgun_webhook_signature(
    *,
    signing_key: str,
    timestamp: str,
    token: str,
    signature: str,
) -> bool:
    """Return True if Mailgun-style ``signature`` matches ``timestamp`` + ``token``.

    Uses the HTTP webhook signing key from the Mailgun dashboard (not the API key
    unless you configure the same value). Constant-time compare on the digest.
    """
    if not signing_key or not signature or not token or not timestamp:
        return False
    msg = f"{timestamp}{token}".encode("utf-8")
    digest = hmac.new(signing_key.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def _parse_json_object(raw: Optional[str]) -> Optional[dict[str, Any]]:
    if not raw or not isinstance(raw, str):
        return None
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return val if isinstance(val, dict) else None


def combine_recipient_hints(form_dict: dict[str, str]) -> str:
    """Join fields providers use for the delivered recipient (used for site hint)."""
    parts: list[str] = []
    for key in ("to", "recipient", "To"):
        v = form_dict.get(key)
        if v:
            parts.append(v)
    env = _parse_json_object(form_dict.get("envelope"))
    if env and isinstance(env.get("to"), list):
        parts.extend(str(x) for x in env["to"] if x)
    return " ".join(parts)


def extract_site_uuid_from_recipient_text(text: str) -> Optional[UUID]:
    """If ``text`` contains ``site.<uuid>`` / ``site_<uuid>``, return that UUID."""
    m = _SITE_UUID_IN_TEXT.search(text)
    if not m:
        return None
    try:
        return UUID(m.group("uuid"))
    except ValueError:
        return None


def _is_pdf_like(*, filename: Optional[str], mime_type: str) -> bool:
    mt = (mime_type or "").split(";", 1)[0].strip().lower()
    if mt == "application/pdf":
        return True
    fn = (filename or "").lower()
    if fn.endswith(".pdf") and mt in ("application/octet-stream", "binary/octet-stream", "application/x-download", ""):
        return True
    return fn.endswith(".pdf") and mt == "application/octet-stream"


def _payload_bytes(part: Message) -> Optional[bytes]:
    """Return decoded non-multipart body, or None if missing."""
    if part.get_content_maintype() == "multipart":
        return None
    try:
        raw = part.get_payload(decode=True)
    except Exception:
        logger.exception("MIME part decode failed")
        return None
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw.encode("utf-8", errors="replace")
    return raw


def extract_attachments_from_rfc822(raw: bytes | str) -> list[tuple[Optional[str], str, bytes]]:
    """Walk a single RFC822 message and collect PDF-like parts (filename, ctype, body)."""
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    msg = message_from_bytes(data, policy=email.policy.default)
    out: list[tuple[Optional[str], str, bytes]] = []
    if not msg.is_multipart():
        body = _payload_bytes(msg)
        if body:
            fn = msg.get_filename()
            ct = msg.get_content_type()
            if _is_pdf_like(filename=fn, mime_type=ct):
                out.append((fn, ct or "application/octet-stream", body))
        return out

    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        body = _payload_bytes(part)
        if not body:
            continue
        fn = part.get_filename()
        ct = part.get_content_type()
        if _is_pdf_like(filename=fn, mime_type=ct):
            out.append((fn, ct or "application/octet-stream", body))
    return out


async def collect_pdf_attachments_from_form(form: FormData) -> tuple[dict[str, str], list[tuple[Optional[str], str, bytes]]]:
    """Parse ``multipart/form-data`` into plain fields plus PDF-like attachment bodies.

    Supports: SendGrid (``attachmentN`` + optional ``attachment-info``), Mailgun
    (``body-mime`` / ``stripped-mime``), and generic uploads (any file part).
    """
    plain: dict[str, str] = {}
    uploads: list[tuple[str, Optional[str], str, bytes]] = []

    for key, value in form.multi_items():
        if isinstance(value, UploadFile):
            body = await value.read()
            if not body:
                continue
            uploads.append(
                (
                    key,
                    value.filename,
                    value.content_type or "application/octet-stream",
                    body,
                )
            )
        else:
            plain[key] = str(value)

    attachment_info = _parse_json_object(plain.get("attachment-info"))
    sendgrid_keys = [u[0] for u in uploads if _SENDGRID_ATTACHMENT_KEY.match(u[0])]

    candidates: list[tuple[Optional[str], str, bytes]] = []

    if sendgrid_keys:
        for key, filename, ctype, body in uploads:
            if not _SENDGRID_ATTACHMENT_KEY.match(key):
                continue
            meta = attachment_info.get(key) if attachment_info else None
            if isinstance(meta, dict):
                filename = meta.get("filename") or filename
                ctype = meta.get("type") or meta.get("content-type") or ctype
            if _is_pdf_like(filename=filename, mime_type=ctype):
                candidates.append((filename, ctype, body))

    if not candidates:
        for mime_key in ("body-mime", "email", "stripped-mime"):
            raw = plain.get(mime_key)
            if not raw:
                continue
            try:
                raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw
                candidates.extend(extract_attachments_from_rfc822(raw_bytes))
            except Exception:
                logger.exception("Failed to parse MIME field %s", mime_key)

    if not candidates:
        for _key, filename, ctype, body in uploads:
            if _is_pdf_like(filename=filename, mime_type=ctype):
                candidates.append((filename, ctype, body))

    return plain, candidates


def enforce_inbound_email_security(
    *,
    settings: Settings,
    plain: dict[str, str],
    headers: Headers,
) -> Optional[str]:
    """Return an error detail string if verification fails; None if OK or skipped."""
    if settings.mailgun_webhook_signing_key:
        ts = plain.get("timestamp")
        tok = plain.get("token")
        sig = plain.get("signature")
        if not ts or not tok or not sig:
            return "Mailgun signing is configured but request lacks timestamp/token/signature fields"
        if not verify_mailgun_webhook_signature(
            signing_key=settings.mailgun_webhook_signing_key,
            timestamp=str(ts),
            token=str(tok),
            signature=str(sig),
        ):
            return "Invalid Mailgun webhook signature"

    hname = (settings.inbound_email_webhook_header_name or "").strip()
    hval = settings.inbound_email_webhook_header_value
    if hname and hval is not None and str(hval) != "":
        # ``Headers.get`` is case-insensitive for header names.
        if headers.get(hname) != hval:
            return f"Missing or invalid required header {hname!r}"

    return None
