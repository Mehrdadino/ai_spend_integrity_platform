#!/usr/bin/env bash
# Start local dependencies (Postgres, MinIO, Redis) plus API, RQ worker, and Vite in one terminal.
# Usage from repo root:  ./scripts/dev.sh   or   bash scripts/dev.sh
#
# Prerequisites: Docker running; backend/.venv from ./scripts/bootstrap-backend-venv.sh (recommended) or pip install -e .;
# frontend deps (cd frontend && npm install). Stop everything with Ctrl+C.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Prefer ``backend/.venv`` over ``/usr/bin/python3`` (macOS is often 3.9.x). Override with BACKEND_PYTHON=/path/to/python.
if [[ -n "${BACKEND_PYTHON:-}" ]]; then
  PY="${BACKEND_PYTHON}"
elif [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
  PY="${ROOT}/backend/.venv/bin/python"
else
  PY="python3"
fi
echo "==> Backend interpreter: ${PY} ($("${PY}" --version 2>&1))"

PIDS=()
cleanup() {
  echo ""
  echo "Stopping dev processes..."
  for p in "${PIDS[@]}"; do
    if kill -0 "$p" 2>/dev/null; then
      kill "$p" 2>/dev/null || true
    fi
  done
  # Give children a moment to exit (uvicorn/vite/npm).
  sleep 0.5
  for p in "${PIDS[@]}"; do
    kill -9 "$p" 2>/dev/null || true
  done
  exit 0
}
trap cleanup INT TERM

echo "==> docker compose up -d (postgres, minio, redis)"
docker compose up -d

echo "==> Waiting for Postgres (pg_isready)..."
for i in {1..45}; do
  if docker compose exec -T postgres pg_isready -U spend -d spend_integrity >/dev/null 2>&1; then
    echo "Postgres is ready."
    break
  fi
  if [[ "$i" -eq 45 ]]; then
    echo "WARNING: Postgres not ready after 45s; seed/webhook hint may fail."
  else
    sleep 1
  fi
done

echo "==> seed-dev-org (dev org + ingest_email_token for email webhook)"
if (cd "$ROOT/backend" && "${PY}" -m app.scripts.seed_dev_org); then
  :
else
  echo "WARNING: seed-dev-org failed. Fix DB/migrations, then from backend/ with your venv active: python -m alembic upgrade head && python -m app.scripts.seed_dev_org (see .cursor/rules/local-dev-stack.mdc)"
fi

echo "==> Inbound email webhook (copy for Mailgun/SendGrid or curl)"
(cd "$ROOT/backend" && "${PY}" -m app.scripts.print_dev_ingest_webhook) || true
echo "Local PDF test: ./scripts/test-inbound-email-local.sh \"\$HOME/Downloads/your-bill.pdf\""
echo "Full email-from-Gmail flow: see .cursor/rules/local-dev-stack.mdc"
echo ""

if [[ "${SKIP_DOCUMENT_WORKER:-}" == "1" ]]; then
  echo "==> SKIP_DOCUMENT_WORKER=1 — not starting RQ document-worker"
else
  echo "==> document worker (RQ, queue documents)"
  (cd "$ROOT/backend" && exec "${PY}" -m app.scripts.run_rq_worker) &
  PIDS+=("$!")
fi

echo "==> API http://127.0.0.1:8000 (uvicorn --reload)"
(cd "$ROOT/backend" && exec "${PY}" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000) &
PIDS+=("$!")

echo "==> frontend http://127.0.0.1:5173 (vite)"
(cd "$ROOT/frontend" && exec npm run dev) &
PIDS+=("$!")

echo ""
echo "Running. Press Ctrl+C to stop API, worker, and Vite (Docker containers stay up)."
echo "To stop containers too: docker compose down"
echo ""

wait
