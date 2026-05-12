"""Print the local inbound-email webhook URL for org slug ``dev``.

Used by ``scripts/dev.sh`` and manual testing so you do not hunt the token in DB.
"""

from __future__ import annotations

import argparse
import sys

from app.db.session import get_session_factory
from app.repositories.organizations import get_organization_by_slug


def main(argv: list[str] | None = None) -> int:
    """Load org ``dev`` and print token or full URL; ``--token-only`` for shell scripts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--token-only",
        action="store_true",
        help="Print only the ingest_email_token (no URL, no extra lines).",
    )
    args = parser.parse_args(argv)

    session = get_session_factory()()
    try:
        org = get_organization_by_slug(session, "dev")
        if org is None:
            print("No organization with slug='dev'. Run: python3 -m app.scripts.seed_dev_org", file=sys.stderr)
            return 1
        if not org.ingest_email_token:
            print(
                "Organization 'dev' has no ingest_email_token (migration 003 + seed). "
                "Run: python3 -m app.scripts.seed_dev_org",
                file=sys.stderr,
            )
            return 1
        token = org.ingest_email_token
        if args.token_only:
            print(token, end="")
            return 0
        base = "http://127.0.0.1:8000/api/v1/webhooks/inbound-email"
        print(f"Inbound email webhook URL:\n  {base}/{token}")
        print("\nLocal curl (simulate SendGrid-style attachment):")
        print(
            f'  curl -sS -X POST "{base}/{token}" \\\n'
            f'    -F "to=bills@example.com" \\\n'
            f'    -F "attachment1=@/path/to/bill.pdf;type=application/pdf"'
        )
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
