"""Create a Seattle site and attach existing bills/documents (dev / pilot setup).

Finds bills whose ``issuer_name`` mentions Seattle (default) or all docs with no
``site_id`` when ``--all-documents`` is set. Updates ``documents.site_id`` and
matching ``bills.site_id`` so §3a prior-bill queries work.

Run from ``backend/`` (Docker Postgres up, ``.env`` / ``DATABASE_URL`` set)::

  assign-seattle-site
  assign-seattle-site --org-slug dev --site-name "Seattle"
  assign-seattle-site --org-id 00000000-0000-0000-0000-000000000001 --dry-run
"""

from __future__ import annotations

import argparse
import sys
import uuid
from typing import Optional

from sqlalchemy import func, select, update

from app.db.session import get_session_factory
from app.models.bill import Bill
from app.models.document import Document
from app.repositories.organizations import get_organization_by_id, get_organization_by_slug
from app.repositories.sites import ensure_site

_DEFAULT_ORG_SLUG = "dev"
_DEFAULT_SITE_NAME = "Seattle"
_DEFAULT_ISSUER_SUBSTR = "seattle"


def _resolve_org_id(session, *, org_slug: str, org_id: Optional[uuid.UUID]) -> uuid.UUID:
    if org_id is not None:
        org = get_organization_by_id(session, org_id)
        if org is None:
            print(f"Organization not found: {org_id}", file=sys.stderr)
            sys.exit(1)
        return org.id
    org = get_organization_by_slug(session, org_slug)
    if org is None:
        print(f"Organization not found for slug={org_slug!r}", file=sys.stderr)
        sys.exit(1)
    return org.id


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a site and assign Seattle (or matching) bills for historical comparison."
    )
    parser.add_argument("--org-slug", default=_DEFAULT_ORG_SLUG, help="Organization slug (default: dev)")
    parser.add_argument("--org-id", type=uuid.UUID, default=None, help="Organization UUID (overrides slug)")
    parser.add_argument("--site-name", default=_DEFAULT_SITE_NAME, help="Site display name to create or reuse")
    parser.add_argument(
        "--issuer-contains",
        default=_DEFAULT_ISSUER_SUBSTR,
        help="Case-insensitive substring on bills.issuer_name (default: seattle)",
    )
    parser.add_argument(
        "--all-documents",
        action="store_true",
        help="Assign every document with null site_id in the org (ignore issuer filter)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without committing",
    )
    args = parser.parse_args()

    factory = get_session_factory()
    session = factory()
    try:
        org_uuid = _resolve_org_id(session, org_slug=args.org_slug, org_id=args.org_id)
        site = ensure_site(session, organization_id=org_uuid, name=args.site_name.strip())

        issuer_needle = (args.issuer_contains or "").strip()
        doc_ids: list[uuid.UUID]
        if args.all_documents:
            doc_ids = list(
                session.scalars(
                    select(Document.id).where(
                        Document.organization_id == org_uuid,
                        Document.site_id.is_(None),
                    )
                ).all()
            )
        elif issuer_needle:
            pattern = f"%{issuer_needle}%"
            doc_ids = list(
                session.scalars(
                    select(Bill.document_id)
                    .where(
                        Bill.organization_id == org_uuid,
                        Bill.issuer_name.isnot(None),
                        func.lower(Bill.issuer_name).like(pattern.lower()),
                    )
                    .distinct()
                ).all()
            )
        else:
            print("Provide --issuer-contains or --all-documents", file=sys.stderr)
            sys.exit(1)

        if not doc_ids:
            print(f"No matching documents for org={org_uuid} (site would be {site.id})")
            return

        if args.dry_run:
            session.rollback()
            print(f"DRY RUN: would create/use site {args.site_name!r} and assign {len(doc_ids)} document(s):")
            for did in doc_ids:
                print(f"  document_id={did}")
            return

        session.execute(
            update(Document)
            .where(Document.id.in_(doc_ids), Document.organization_id == org_uuid)
            .values(site_id=site.id)
        )
        session.execute(
            update(Bill)
            .where(Bill.document_id.in_(doc_ids), Bill.organization_id == org_uuid)
            .values(site_id=site.id)
        )
        session.commit()
        print(f"site_id={site.id} name={site.name!r} organization_id={org_uuid}")
        print(f"Updated documents={len(doc_ids)} (and matching bills)")
        print("Re-open a bill in the UI or call GET .../bill/prior-bills to see history.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
