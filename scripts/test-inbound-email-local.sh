#!/usr/bin/env bash
# Simulate SendGrid-style multipart POST to the local inbound-email webhook (step 1e).
# Requires API up (e.g. ./scripts/dev.sh) and dev org with ingest_email_token (seed-dev-org).
#
# Usage from repo root:
#   ./scripts/test-inbound-email-local.sh /path/to/bill.pdf

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${BACKEND_PYTHON:-}" ]]; then
  PY="${BACKEND_PYTHON}"
elif [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
  PY="${ROOT}/backend/.venv/bin/python"
else
  PY="python3"
fi
PDF="${1:?Usage: $0 /path/to/real-bill.pdf}"

if [[ ! -f "$PDF" ]]; then
  cat >&2 <<EOF
File not found: ${PDF}

The path must be a real PDF on this machine (not the documentation example
"/full/path/to/some-bill.pdf"). Examples:

  $0 "\$HOME/Downloads/my-utility-bill.pdf"
  $0 "/Users/$(whoami)/Desktop/invoice.pdf"

From repo root: ${ROOT}
EOF
  exit 1
fi

echo "==> Reading ingest token from DB (org slug=dev)..."
TOKEN="$(cd "$ROOT/backend" && "${PY}" -m app.scripts.print_dev_ingest_webhook --token-only)" || {
  echo "Could not read ingest token (DB up? migrations? run: cd ${ROOT}/backend && \"${PY}\" -m alembic upgrade head && \"${PY}\" -m app.scripts.seed_dev_org)" >&2
  exit 1
}
if [[ -z "${TOKEN}" ]]; then
  echo "ingest_email_token is empty after seed; run: cd ${ROOT}/backend && \"${PY}\" -m app.scripts.seed_dev_org" >&2
  exit 1
fi

URL="http://127.0.0.1:8000/api/v1/webhooks/inbound-email/${TOKEN}"
echo "==> POST (SendGrid-style attachment1) → ${URL}"
echo "==> PDF file: ${PDF}"
curl -sS -w "\nHTTP %{http_code}\n" -X POST "$URL" \
  -F "to=bills@example.com" \
  -F "attachment1=@${PDF};type=application/pdf"
echo ""
