#!/usr/bin/env python3
"""Write cross-site comparison demo PDFs to ``backend/tests/fixtures/cross_site_pdfs/``.

Run from repo root::

    cd backend && . .venv/bin/activate && python scripts/generate_cross_site_pdfs.py

Upload in numeric filename order (see README in that folder). Site A's March bill
(``03-upload-last-...``) must be uploaded **after** the other two core PDFs.
"""

from __future__ import annotations

import os
import sys

# Allow ``tests.support`` import when invoked as a script.
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from tests.support.cross_site_bill_pdf import write_cross_site_pdfs_to_dir  # noqa: E402


def main() -> None:
    out_dir = os.path.join(_BACKEND_ROOT, "tests", "fixtures", "cross_site_pdfs")
    paths = write_cross_site_pdfs_to_dir(out_dir, include_optional=True)
    print(f"Wrote {len(paths)} PDFs to {out_dir}")
    for p in paths:
        print(f"  {os.path.basename(p)}")


if __name__ == "__main__":
    main()
