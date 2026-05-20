"""§3b extraction-quality signals from ``bills.summary`` provenance (no prior bill).

``bill_sync`` merges text/OCR stats and structuring provenance into ``summary`` JSONB.
These rules surface LLM fallbacks, sparse PDF text, and empty line lists for pilot review.
"""

from __future__ import annotations

from typing import Any

from app.models.bill import Bill
from app.schemas.comparison import ComparisonFindingResponse, ComparisonSeverity
from app.services.comparison.rules_config import EXTRACTION_MIN_LINE_COUNT


def _finding(
    *,
    rule_id: str,
    severity: ComparisonSeverity,
    title: str,
    summary: str,
    evidence: dict[str, Any] | None = None,
) -> ComparisonFindingResponse:
    return ComparisonFindingResponse(
        rule_id=rule_id,
        severity=severity,
        title=title,
        summary=summary,
        evidence=evidence or {},
    )


def _summary_dict(bill: Bill) -> dict[str, Any]:
    raw = bill.summary
    return dict(raw) if isinstance(raw, dict) else {}


def _check_structured_fallback(summary: dict[str, Any]) -> ComparisonFindingResponse | None:
    """LLM structuring failed and deterministic sample lines were stored."""
    via = str(summary.get("structured_via") or "")
    if via != "deterministic_fallback":
        return None
    err = summary.get("structured_error")
    note = summary.get("structured_note")
    return _finding(
        rule_id="extraction_structured_fallback",
        severity="warning",
        title="Line items may not match this PDF",
        summary=(
            "Structured extraction fell back to a deterministic sample because LLM structuring failed. "
            "Reprocess after fixing EXTRACTION_LLM_* settings, or review line items manually."
        ),
        evidence={
            "structured_via": via,
            "structured_error": str(err) if err else None,
            "structured_note": str(note) if note else None,
        },
    )


def _check_stub_without_llm(summary: dict[str, Any]) -> ComparisonFindingResponse | None:
    """Dev/CI stub lines while PDF text exists but no API key is configured."""
    via = str(summary.get("structured_via") or "")
    if via != "deterministic_stub":
        return None
    if not summary.get("structured_note"):
        return None
    if summary.get("text_has_usable_text") is False:
        return None
    return _finding(
        rule_id="extraction_no_llm_key",
        severity="info",
        title="Structured line items need an LLM API key",
        summary=str(summary.get("structured_note")),
        evidence={"structured_via": via},
    )


def _check_low_text_quality(summary: dict[str, Any]) -> ComparisonFindingResponse | None:
    """Sparse embedded text or OCR-needed scans reduce extraction reliability."""
    method = str(summary.get("text_extraction_method") or "")
    if method == "skipped_unsupported_mime":
        return None
    needs_ocr = summary.get("text_needs_ocr") is True
    has_usable = summary.get("text_has_usable_text")
    if not needs_ocr and has_usable is not False:
        return None
    char_count = summary.get("text_char_count")
    return _finding(
        rule_id="extraction_low_text_quality",
        severity="warning",
        title="PDF text may be too sparse for reliable extraction",
        summary=(
            "Embedded text was missing or very short on this document. "
            "Scan quality, OCR settings, or manual line review may be needed before trusting anomalies."
        ),
        evidence={
            "text_extraction_method": method,
            "text_needs_ocr": needs_ocr,
            "text_has_usable_text": has_usable,
            "text_char_count": char_count,
        },
    )


def _check_no_normalized_lines(bill: Bill, summary: dict[str, Any]) -> ComparisonFindingResponse | None:
    """Zero lines after normalization blocks most integrity math."""
    n_items = len(list(bill.line_items))
    if n_items > 0:
        return None
    # Synthetic/unit-test bills often omit ``summary``; only flag real pipeline bills.
    if not summary.get("source_extraction_version") and summary.get("line_count") is None:
        return None
    line_count = summary.get("line_count")
    if isinstance(line_count, int) and line_count > 0:
        return None
    return _finding(
        rule_id="extraction_no_line_items",
        severity="warning",
        title="No bill line items were normalized",
        summary=(
            "This bill has no normalized charge lines. Comparison and share-of-total rules "
            "cannot run until extraction produces at least one line item."
        ),
        evidence={
            "line_count": line_count if isinstance(line_count, int) else 0,
            "line_items_on_bill": n_items,
        },
    )


def _check_few_line_items(bill: Bill, summary: dict[str, Any]) -> ComparisonFindingResponse | None:
    """Very short line lists on text-rich PDFs often mean incomplete LLM structuring."""
    if summary.get("text_has_usable_text") is not True:
        return None
    n_items = len(list(bill.line_items))
    if n_items == 0 or n_items >= EXTRACTION_MIN_LINE_COUNT:
        return None
    return _finding(
        rule_id="extraction_few_line_items",
        severity="info",
        title="Few line items extracted from a text PDF",
        summary=(
            f"Only {n_items} line(s) were structured from a document with usable embedded text. "
            "Utility bills often have more rows—confirm extraction did not drop riders or taxes."
        ),
        evidence={"line_count": n_items, "min_expected": EXTRACTION_MIN_LINE_COUNT},
    )


def evaluate_extraction_quality(bill: Bill) -> list[ComparisonFindingResponse]:
    """Run provenance-based extraction warnings for one normalized bill."""
    summary = _summary_dict(bill)
    findings: list[ComparisonFindingResponse] = []
    for check in (
        lambda: _check_structured_fallback(summary),
        lambda: _check_stub_without_llm(summary),
        lambda: _check_low_text_quality(summary),
        lambda: _check_no_normalized_lines(bill, summary),
        lambda: _check_few_line_items(bill, summary),
    ):
        result = check()
        if result is not None:
            findings.append(result)
    return findings
