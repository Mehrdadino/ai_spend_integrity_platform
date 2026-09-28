# Contributing

Thanks for helping improve Spend Integrity.

## Before you start

- Open an issue for larger changes so the approach can be agreed first.
- Keep pull requests focused. A bug fix and an unrelated refactor should be separate.
- Do not commit secrets, `.env` files, customer bills, or private PDFs. Local copies of `.env` stay on your machine. Use `backend/.env.example` and `frontend/.env.example` when you add a new setting.

## Development

Prerequisites and `./scripts/dev.sh` are in the [README](README.md).

When you change the database models, add an Alembic revision under `backend/alembic/versions/` and apply it locally:

```bash
cd backend && . .venv/bin/activate && python -m alembic upgrade head
```

After Python changes:

```bash
cd backend && . .venv/bin/activate && python -m compileall -q app && python -c "from app.main import app"
```

Run the tests that cover your change (`python -m pytest` from `backend/`).

New or edited Python modules, public functions, and non-obvious logic need a short comment or docstring that states intent, especially where `organization_id` scopes data or where Postgres metadata and object-storage bytes are both involved.

If a change alters a user-visible flow, API, table, worker stage, or the dev stack described in the roadmaps, update [product_roadmap.md](product_roadmap.md) and [eng_roadmap.md](eng_roadmap.md) in the same pull request.

## Pull requests

- Describe what changed and why.
- Note how you tested it.
- Screenshots help for UI changes.

## Conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
