# Security

## Reporting a vulnerability

Please do not file a public GitHub issue for a security problem, and do not include passwords, API keys, tokens, or customer documents in an issue or pull request.

Use [GitHub private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) for this repository. If that is unavailable, contact the maintainer through GitHub without posting the secret itself.

## Secrets in this repository

Tracked files must not contain private keys, cloud credentials, LLM API keys, or production JWT secrets.

- `backend/.env` and `frontend/.env` are gitignored. Put real values only there.
- `backend/.env.example` and `frontend/.env.example` are safe templates with empty secrets.
- Docker Compose passwords (`spend`, `minio_minio_minio`) and the dev admin login (`admin@dev.local` / `Dev-Admin-Change1!`) are for a machine-local stack only.
- The default `JWT_SECRET_KEY` (`change-me-in-production`) is rejected when `APP_ENV=production`.

If a real key was ever committed, pasted into a public place, or shipped in a screenshot, revoke it at the provider and issue a new one. Deleting the file later does not remove it from git history.

## Production configuration

The API refuses to start in production when any of these are unsafe (`backend/app/startup_checks.py`):

- `JWT_SECRET_KEY` missing, shorter than 32 characters, or one of the known dev placeholders
- `AUTH_ALLOW_DEV_ORG_HEADER=true` (the `X-Organization-Id` bypass)
- `REDIS_URL` empty (rate limits fail closed without Redis)
- `RATE_LIMIT_ENABLED=false`

Also set `CORS_ORIGINS` to your real frontend origin, point `S3_*` at credentials that are not the MinIO dev user, and send mail through your own SMTP provider. Leave `AUTH_ALLOW_REGISTRATION=false` unless you intentionally want open sign-up; the intended production path is organization invites.
