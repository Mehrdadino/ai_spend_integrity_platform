"""CLI: register a file as a document (step 1a — dev / smoke test).

Usage (from `backend/` with deps installed and docker compose up):

  uv run register-document --file /path/to/bill.pdf --org-slug dev --mime application/pdf
  uv run register-document --file ./sample.pdf --org-slug dev --site-name "Store 1"

Uses **two database sessions** on purpose: commit org/site first so a failed
S3/``Document`` insert does not roll back the tenant row. ``org_id`` is copied
before closing the first session to avoid detached-instance access.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.db.session import get_session_factory
from app.repositories.organizations import ensure_organization
from app.repositories.sites import ensure_site
from app.services.document_registry import DuplicateDocumentError, register_document_bytes
from app.services.storage import ensure_documents_bucket_exists


def main() -> None:
    """Parse argv, ensure bucket, commit org/site, then register bytes + commit."""
    parser = argparse.ArgumentParser(description="Register a document in Postgres + object storage (step 1a).")
    parser.add_argument("--file", required=True, type=Path, help="Path to the file to store")
    parser.add_argument("--org-slug", default="dev", help="Organization slug (created if missing)")
    parser.add_argument("--org-name", default="Dev Organization", help="Display name when creating org")
    parser.add_argument("--site-name", default=None, help="Optional site name (created if missing)")
    parser.add_argument(
        "--mime",
        default="application/pdf",
        help="MIME type stored on the object (default: application/pdf)",
    )
    args = parser.parse_args()

    path: Path = args.file
    if not path.is_file():
        print(f"Not a file: {path}", file=sys.stderr)
        sys.exit(1)

    body = path.read_bytes()
    ensure_documents_bucket_exists()

    factory = get_session_factory()
    session = factory()
    try:
        org = ensure_organization(session, name=args.org_name, slug=args.org_slug)
        site_id = None
        if args.site_name:
            site = ensure_site(session, organization_id=org.id, name=args.site_name)
            site_id = site.id
        session.commit()
        # UUID is safe to retain after close (not ORM lazy state).
        org_id = org.id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    session = factory()
    try:
        doc = register_document_bytes(
            session,
            organization_id=org_id,
            site_id=site_id,
            body=body,
            mime_type=args.mime,
            source="upload",
            processing_status="pending",
        )
        session.commit()
        print(f"document_id={doc.id}")
        print(f"s3://{doc.bucket}/{doc.object_key}")
        print(f"sha256={doc.sha256}")
    except DuplicateDocumentError as e:
        session.rollback()
        print(f"Duplicate: org={e.organization_id} sha256={e.sha256}", file=sys.stderr)
        sys.exit(2)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
