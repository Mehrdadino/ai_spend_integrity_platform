# AI Spend Integrity Platform

Upload utility bills, extract line items, and review spend anomalies across sites.

Phase 1 is a local-first app: a FastAPI backend, a React UI, and a background worker. Postgres stores metadata and pipeline state. MinIO (S3-compatible) stores the original files.

## What it does

- Sign in, invite teammates, and scope data by organization.
- Create sites (locations) and upload PDF bills against a site.
- Extract embedded PDF text, fall back to Tesseract OCR for scans, and optionally structure line items with an OpenAI-compatible LLM.
- Compare a bill to earlier bills at the same site, and to peer sites.
- Review anomalies (approve, dismiss, flag, reopen) with notes.

Without an LLM API key, extraction still runs and stores deterministic sample line items so you can exercise the pipeline.

## Stack

| Piece | Role |
| --- | --- |
| FastAPI + SQLAlchemy + Alembic | API and Postgres schema |
| Redis + RQ | Document and comparison jobs |
| MinIO | Original file bytes |
| Vite + React + TypeScript | Web UI |
| Mailpit | Local inbox for invites, login OTP, and password reset |

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (Postgres, MinIO, Redis, Mailpit)
- [Node.js](https://nodejs.org/) 18 or newer and npm
- [uv](https://docs.astral.sh/uv/) for the Python environment (`scripts/dev.sh` can install a venv on first run)
- For scan/OCR bills: [Tesseract](https://github.com/tesseract-ocr/tesseract) and Poppler (`pdftoppm`). Embedded-text PDFs do not need them.

macOS examples:

```bash
brew install tesseract poppler
```

## Quick start

From the repository root:

```bash
./scripts/dev.sh
```

That command starts Docker services, creates `backend/.venv` if needed, migrates and seeds a dev organization and admin user, then runs the API, the RQ worker, and Vite.

| Service | URL |
| --- | --- |
| Web app | http://127.0.0.1:5173 |
| API | http://127.0.0.1:8000 |
| API docs | http://127.0.0.1:8000/docs |
| Mailpit inbox | http://127.0.0.1:8025 |
| MinIO console | http://127.0.0.1:9001 |

Ctrl+C stops the API, worker, and Vite. Containers keep running until you run `docker compose down`.

### Sign in (local only)

`scripts/dev.sh` seeds a platform admin:

- Email: `admin@dev.local`
- Password: `Dev-Admin-Change1!`

Override those with `DEV_ADMIN_EMAIL` and `DEV_ADMIN_PASSWORD` before seeding. Local registration is open when you start the API through `dev.sh`. Do not expose this stack on a public network with those defaults.

Then, in the sidebar, select the **Dev Organization**, create a site on the **Sites** tab, select that site, and upload PDFs on **Upload**. The day-to-day UI flow is in [instructions.md](instructions.md).

## Configuration

Copy the examples and edit the copies. Those copies are gitignored.

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

`scripts/dev.sh` works without a filled-in `.env` for the default Docker stack. Add an LLM key only in `backend/.env`:

```bash
EXTRACTION_LLM_API_KEY=
EXTRACTION_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
EXTRACTION_LLM_MODEL=gemini-2.5-flash
```

Restart `./scripts/dev.sh`, then reprocess a document in the viewer.

Docker Compose publishes local-only credentials (`spend` / `spend` for Postgres, `minio` / `minio_minio_minio` for MinIO). They match the defaults in `backend/app/config.py`. Replace them before any shared or production deployment. Production also requires a unique `JWT_SECRET_KEY` (32+ characters), `AUTH_ALLOW_DEV_ORG_HEADER=false`, Redis, and rate limiting. Details are in [SECURITY.md](SECURITY.md).

## Tests

From `backend/` with the virtualenv active:

```bash
python -m compileall -q app
python -m pytest
```

## Project layout

```text
backend/          FastAPI app, Alembic migrations, RQ worker, tests
frontend/         Vite + React UI
scripts/dev.sh    One-command local stack
docker-compose.yml
```

Product intent is in [product_roadmap.md](product_roadmap.md). What is implemented, by engineering step, is in [eng_roadmap.md](eng_roadmap.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Security

See [SECURITY.md](SECURITY.md). Do not open a public issue that contains passwords, API keys, or customer bill data.

## License

[MIT](LICENSE). Copyright (c) 2026 mehrdadino.
