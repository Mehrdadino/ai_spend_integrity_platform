"""Presigned GET URLs for stored document bytes (browser preview / download).

Org scoping stays in the API layer; this module only checks that the row has a
finalized object (``sha256`` / ``byte_size``) before signing.
"""

from __future__ import annotations

from app.models.document import Document
from app.services.storage import generate_presigned_get_url


def presigned_get_url_for_document(doc: Document, *, expires_in: int) -> str:
    """Return a presigned GET URL for ``doc``'s ``bucket``/``object_key``.

    Raises ``ValueError`` if the upload was never finalized (no hash/size yet).
    """
    if doc.sha256 is None or doc.byte_size is None:
        raise ValueError("Document has no finalized object in storage yet")
    return generate_presigned_get_url(
        bucket=doc.bucket,
        key=doc.object_key,
        expires_in=expires_in,
        response_content_type=doc.mime_type,
    )
