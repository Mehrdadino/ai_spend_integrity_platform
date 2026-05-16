#!/usr/bin/env bash
# Start local dependencies (Postgres, MinIO, Redis) plus API, RQ worker, and Vite in one terminal.
# Usage from repo root:  ./scripts/dev.sh   or   bash scripts/dev.sh
#
# Prerequisites: Docker running; ``uv`` on PATH (see bootstrap script). This script creates
# ``backend/.venv`` on first run and runs ``uv sync`` when deps change — no manual pip needed.
# frontend deps (cd frontend && npm install). Stop everything with Ctrl+C.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Backend venv: one-time create via bootstrap; ``uv sync`` on each dev start (fast no-op when up to date).
ensure_backend_venv() {
  if [[ -n "${BACKEND_PYTHON:-}" ]]; then
    return 0
  fi
  if [[ ! -x "${ROOT}/backend/.venv/bin/python" ]]; then
    echo "==> backend/.venv missing — running ./scripts/bootstrap-backend-venv.sh"
    "${ROOT}/scripts/bootstrap-backend-venv.sh"
    return 0
  fi
  if command -v uv >/dev/null 2>&1; then
    echo "==> backend Python deps (uv sync; skips work when already current)"
    (cd "${ROOT}/backend" && uv sync)
  else
    echo "WARNING: uv not on PATH — using existing backend/.venv as-is."
    echo "         After git pull, run: cd backend && uv sync   (or install uv and re-run dev.sh)"
  fi
}
ensure_backend_venv

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

echo "==> seed-dev-org (dev org for X-Organization-Id / VITE_ORG_ID)"
if (cd "$ROOT/backend" && "${PY}" -m app.scripts.seed_dev_org); then
  :
else
  echo "WARNING: seed-dev-org failed. Fix DB/migrations, then from backend/ with your venv active: python -m alembic upgrade head && python -m app.scripts.seed_dev_org (see .cursor/rules/local-dev-stack.mdc)"
fi

echo "==> seed-dev-user (JWT admin for Connection sign-in)"
if (cd "$ROOT/backend" && "${PY}" -m app.scripts.seed_dev_user); then
  :
else
  echo "WARNING: seed-dev-user failed. Run: cd backend && python -m alembic upgrade head && python -m app.scripts.seed_dev_user"
fi

echo ""

if [[ "${SKIP_DOCUMENT_WORKER:-}" == "1" ]]; then
  echo "==> SKIP_DOCUMENT_WORKER=1 — not starting RQ document-worker"
else
  echo "==> document worker (RQ, queue documents; SimpleWorker on macOS — see run_rq_worker docstring)"
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
