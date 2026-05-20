"""Assess whether an uploaded file should be treated as a utility bill (post-extraction).

Runs **after** 2a/2b succeed so corrupt PDFs still become ``failed`` (pipeline errors).
When assessment fails, the worker sets ``processing_status=unsupported`` and **does not**
create a ``bills`` row or run comparison — avoiding fake stub lines and nonsense anomalies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.constants.document_processing import (
    UNSUPPORTED_INSUFFICIENT_STRUCTURE,
    UNSUPPORTED_LLM_FALLBACK,
    UNSUPPORTED_NO_LINE_ITEMS,
    UNSUPPORTED_STUB_IGNORED_TEXT,
    UNSUPPORTED_UNSUPPORTED_MIME,
)
from app.constants.normalization import SPEND_DOMAIN_UNSPECIFIED
from app.models.document import Document
from app.services.normalization.from_extraction import NormalizedBillDraft

_USER_MESSAGES: dict[str, str] = {
    UNSUPPORTED_STUB_IGNORED_TEXT: (
        "This PDF was not turned into bill line items because structured extraction is not configured "
        "(EXTRACTION_LLM_API_KEY). After adding a key, you can reprocess this same file. Otherwise "
        "delete this document and upload a utility invoice PDF."
    ),
    UNSUPPORTED_LLM_FALLBACK: (
        "Structured extraction failed for this PDF, so it was not saved as a bill. If this is a real "
        "utility invoice, fix EXTRACTION_LLM_* and reprocess the same file. If the file is not a bill, "
        "delete it and upload a different PDF."
    ),
    UNSUPPORTED_UNSUPPORTED_MIME: (
        "This file type is not supported. Delete this document and upload a PDF utility invoice."
    ),
    UNSUPPORTED_NO_LINE_ITEMS: (
        "Nothing on this document looks like utility bill line items. Delete it and upload a utility "
        "invoice PDF (reprocess cannot change the file contents)."
    ),
    UNSUPPORTED_INSUFFICIENT_STRUCTURE: (
        "Extracted data is too sparse for a utility bill. Delete this document and upload a proper "
        "utility invoice PDF."
    ),
}


@dataclass(frozen=True)
class DocumentValidityAssessment:
    """Outcome of ``assess_document_validity`` for the worker and API."""

    is_utility_bill: bool
    reason_code: str | None
    user_message: str | None

    @staticmethod
    def supported() -> DocumentValidityAssessment:
        return DocumentValidityAssessment(True, None, None)

    @staticmethod
    def unsupported(*, reason_code: str) -> DocumentValidityAssessment:
        return DocumentValidityAssessment(
            False,
            reason_code,
            _USER_MESSAGES.get(
                reason_code,
                "This document was not recognized as a utility bill.",
            ),
        )


def _lines_with_amount(bundle: NormalizedBillDraft) -> int:
    return sum(1 for ln in bundle.lines if ln.amount is not None)


def assess_document_validity(
    *,
    document: Document,
    bundle: NormalizedBillDraft,
    provenance: dict[str, Any],
) -> DocumentValidityAssessment:
    """Return whether we should create a normalized bill and run comparison rules.

    Uses extraction provenance (``structured_via``, text stats) and normalized content only.
    Does not raise — the worker maps ``unsupported`` to ``processing_status``.
    """
    _ = document  # reserved for future MIME-specific rules
    structured_via = str(provenance.get("structured_via") or "")
    text_method = str(provenance.get("text_extraction_method") or "")
    has_usable_text = provenance.get("text_has_usable_text") is True

    if text_method == "skipped_unsupported_mime":
        return DocumentValidityAssessment.unsupported(reason_code=UNSUPPORTED_UNSUPPORTED_MIME)

    if structured_via == "deterministic_fallback":
        return DocumentValidityAssessment.unsupported(reason_code=UNSUPPORTED_LLM_FALLBACK)

    if structured_via == "deterministic_stub" and has_usable_text:
        return DocumentValidityAssessment.unsupported(reason_code=UNSUPPORTED_STUB_IGNORED_TEXT)

    if not bundle.lines:
        return DocumentValidityAssessment.unsupported(reason_code=UNSUPPORTED_NO_LINE_ITEMS)

    if _lines_with_amount(bundle) == 0 and bundle.period_end is None and not bundle.issuer_name:
        return DocumentValidityAssessment.unsupported(reason_code=UNSUPPORTED_INSUFFICIENT_STRUCTURE)

    # Optional weak signal: wholly unspecified domain with no monetary lines.
    if (
        bundle.spend_domain == SPEND_DOMAIN_UNSPECIFIED
        and _lines_with_amount(bundle) == 0
        and bundle.period_end is None
    ):
        return DocumentValidityAssessment.unsupported(reason_code=UNSUPPORTED_INSUFFICIENT_STRUCTURE)

    return DocumentValidityAssessment.supported()
