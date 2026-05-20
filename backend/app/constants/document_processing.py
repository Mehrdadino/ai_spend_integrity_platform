"""Worker ``documents.processing_status`` values and validity reason codes.

``failed`` = our pipeline could not process the file (corrupt PDF, validation error, OCR failure).
``unsupported`` = file was processed but is not treated as a utility bill (user/content issue).
"""

from __future__ import annotations

PROCESSING_AWAITING_OBJECT = "awaiting_object"
PROCESSING_QUEUED = "queued"
PROCESSING_PENDING = "pending"
PROCESSING_RECEIVED = "received"
PROCESSING_EXTRACTED = "extracted"
PROCESSING_FAILED = "failed"
PROCESSING_UNSUPPORTED = "unsupported"

# ``documents.unsupported_reason`` stores a stable code; UI maps to user-facing copy.
UNSUPPORTED_STUB_IGNORED_TEXT = "stub_ignored_text"
UNSUPPORTED_LLM_FALLBACK = "llm_structuring_failed"
UNSUPPORTED_UNSUPPORTED_MIME = "unsupported_file_type"
UNSUPPORTED_NO_LINE_ITEMS = "no_line_items"
UNSUPPORTED_INSUFFICIENT_STRUCTURE = "insufficient_bill_structure"

# Re-running the worker on the **same** S3 object may change the outcome (extraction config only).
REPROCESS_MAY_HELP_UNSUPPORTED_CODES = frozenset(
    {
        UNSUPPORTED_STUB_IGNORED_TEXT,
        UNSUPPORTED_LLM_FALLBACK,
    },
)
