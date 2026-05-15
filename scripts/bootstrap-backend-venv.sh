#!/usr/bin/env bash
# Create ``backend/.venv`` with a working CPython 3.12 (recommended on macOS when
# Homebrew's ``python3.12 -m venv`` fails: ``ensurepip`` / ``pyexpat`` vs ``/usr/lib/libexpat``).
#
# Uses ``uv`` (https://github.com/astral-sh/uv) to download a standalone CPython build,
# then ``uv sync`` (``backend/uv.lock``) to install project dependencies into ``.venv``.
#
# Run from repo root:
#   ./scripts/bootstrap-backend-venv.sh
#
# Afterward, add ``~/.local/bin`` to PATH (or restart the terminal) so ``uv`` stays available.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

if ! command -v uv >/dev/null 2>&1; then
  echo "==> uv not found; installing to ~/.local/bin (one-time)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="${HOME}/.local/bin:${PATH}"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv still not on PATH. Add: export PATH=\"\$HOME/.local/bin:\$PATH\"" >&2
  exit 1
fi

echo "==> Removing old backend/.venv (if any)"
rm -rf .venv

echo "==> uv venv --python 3.12"
uv venv --python 3.12 .venv

echo "==> uv sync (install locked deps from pyproject.toml / uv.lock)"
uv sync

echo ""
echo "==> Success:"
.venv/bin/python --version
echo "Interpreter: ${ROOT}/backend/.venv/bin/python"
echo ""
echo "In Cursor: Python: Select Interpreter → backend/.venv/bin/python"
echo "Then from repo root: ./scripts/dev.sh"
