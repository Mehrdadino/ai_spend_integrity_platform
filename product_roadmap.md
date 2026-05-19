COMPANY VISION
AI-Powered Spend Integrity Platform

Long-term vision:

Continuously verify vendor charges, recurring spend, and operational billing behavior.

PHASE 1 — Fast MVP (0–4 Months)
Goal

Ship something real FAST.

Not infrastructure.
Not ML research.
Not perfect parsing.

Just:

“upload bills → get useful anomaly insights.”

---

## Implementation status (repository) — 2026-05-19

**Why this section:** align the product roadmap with what is already built so future work starts from the correct checkpoint.

### Built so far (Phase 1 — ingestion through review)

- **Stack in repo:** Python **FastAPI**, **PostgreSQL**, **MinIO**, **Redis + RQ**, **Vite + React + TypeScript** UI. Docker Compose runs Postgres, MinIO, and Redis locally.
- **Document ingestion:** presigned upload + CLI; optional **display name** on upload; **SHA-256 dedupe** per org (re-upload allowed after soft delete); **Organizations** tab (list/create tenants); **Documents** tab with viewer, bill panel, **reprocess**, and **auto-refresh** while the worker runs.
- **Sites & upload context:** **Connection** panel — active org, **site picker for uploads** (stored per org), create site; assign or change **site** on a document in the viewer (**`PATCH …/site`**). Comparison history is per **site** (location), not per utility type.
- **Background pipeline:** RQ worker loads PDF bytes from S3, extracts **embedded text** (`pypdf`), falls back to **Tesseract OCR** for scan-only PDFs / image MIME types, optionally structures via **LLM** when `EXTRACTION_LLM_API_KEY` is set, validates **`generic-bill-v1`** (**2b**), persists **`document_raw_extractions`** (**2a**), normalizes to **`bills` / `bill_line_items`** (**2c–2d**).
- **Without LLM key:** deterministic sample line items still run for dev/CI; bill summary notes that PDF text was extracted but structuring needs an API key.
- **Auth (P1/P3):** **Login UI** + JWT (**remember this device** = 30 days, else ~12h session); email 2FA when **`SMTP_HOST`** is set; **Account** tab; **forgot/reset password**; password policy; **invite-only registration** in production (`AUTH_ALLOW_REGISTRATION=false`, open in dev via **`dev.sh`**).
- **Org teams (B2B):** **`organization_members`** with per-org roles **`org_admin`** | **`member`** | **`viewer`**; email **invites** + **`POST /auth/accept-invite`**; **Team** panel on Organizations (org admin); viewers read-only; members upload/review; org admins manage sites/team/delete.
- **Platform admin** still sees all orgs; dev **`X-Organization-Id`** when `AUTH_ALLOW_DEV_ORG_HEADER=true`.
- **Production hardening:** Redis **rate limits** (e.g. **3/15min** per email on forgot/register/invite, **5/15min** login, **10/min** per IP); **lockout** after **5** failed sign-ins; security headers; production startup validation.
- **§3a prior bills:** `get_prior_bills_for_bill` + **`GET …/bill/prior-bills`** (same org, same `site_id`; period ordering); prior-bill table in document viewer.
- **§3b + §3d + §4:** **`GET …/bill/comparison`** persists anomalies; rule pack **`comparison-v1.1`** — **single-bill integrity** on every bill (no prior): header vs lines, duplicate line fingerprints, high fee share, penalty-style fee labels, missing period dates, credits vs charges; with history: MoM total, new fee lines; **`GET /api/v1/anomalies`** (+ detail) with **template explanations** and **grounding** from saved evidence; **`POST …/materialize-comparisons`** for inbox **Refresh**.
- **§3e comparison backfill:** After worker upsert, **bounded site-wide** comparison when the bill has a `site_id` (correct priors after mid-timeline insert/delete). **Site change** refreshes the new site (via backfill) and the **previous** site when the bill moved. **Soft delete** triggers site-wide refresh. Keyset walk; cap `SITE_BILL_REFRESH_MAX_BILLS` (default 10,000).
- **§5 review workflow:** `review_status` + **`anomaly_review_events`**; **`POST …/anomalies/{id}/review`**; inbox **Review status** filter; per-row **Actions** (approve / dismiss / flag / reopen) with **§5e notes** and **History**.
- **Anomalies inbox UX:** signals **grouped by bill/document**; optional **display name** on list/API; **Filter by bill** — searchable, paginated **`GET /documents/browse`**; **View bill** on group; row click opens document (text can be highlighted without navigating). **Documents** tab **Signals** link and viewer **View in signals inbox** jump to filtered Anomalies.
- **Document labels & delete:** optional **`display_name`** — set on upload, edit/clear in viewer, **`PATCH …/display-name`**; soft delete **`DELETE …/documents/{id}`** + UI **Delete** (S3 bytes retained until hard delete).

### Still to build for Phase 1 MVP

- **Auth / org (deferred):** SSO (OIDC/SAML), email verification on signup/change-email, revoke-all-sessions, auth audit log, TOTP app 2FA, per-org domain allowlist, seat billing.
- **§3c** site-to-site comparables (cross-location; not started).
- **Real-bill pilot** — production LLM structuring quality and more **single-bill** / domain rules on real PDFs.
- **P2** — worker retries and upload idempotency hardening.

### Recommended next focus (product ↔ eng)

- **Real-bill pilot** — `EXTRACTION_LLM_API_KEY`, validate normalization on real utility PDFs; extend **single-bill integrity** (extraction-quality warnings, tax share, domain packs).
- **§3c** — site-to-site comparables when a pilot needs cross-location views.
- **P2** — worker retries + idempotency.
- **Comparison chain by utility type** — optional split of priors by `spend_domain` / service (today: one chain per site only).

### Possible future work (comparison breadth)

- **§3c — site-to-site comparables:** compare normalized usage/charges across locations when categories and units align, with explicit “not comparable” outcomes. **Not started** (see [`eng_roadmap.md`](eng_roadmap.md) §0.0).
- **Prior chain by bill type** — e.g. Seattle electric vs Seattle water on the same site as separate comparison chains (workaround today: separate sites).

### Deferred / optional (later — not blocking MVP demo)

| Item | Why defer |
|------|-----------|
| **`total_amount` on `raw_payload`** | Normalized total is sum-of-lines today; add when we need “amount due” vs line-sum integrity checks. |
| **`document_id` filter on `GET /anomalies`** | Inbox filters by document client-side after load; add server-side filter at scale. |
| **OCR quality hardening** | Tune DPI/thresholds, rendering, and scan coverage tests when scan-heavy bills fail extraction. |
| **§3e at extreme scale** | Raise caps or tiered refresh if a site exceeds **10k** bills. |
| **§2e internal raw vs normalized viewer** | Support/debug tool beyond the current debug JSON panel. |
| **§4b LLM “polish” on explanations** | Templates shipped; LLM optional behind a flag. |
| **Inbound email ingestion (eng 1e–1g)** | Presigned upload + CLI is enough for Phase 1. |
| **P2 retries / idempotency** | Not started; see eng roadmap. |

---

Product Scope

Very narrow:

Utility Bill Intelligence

For:

multi-location businesses,
commercial properties,
refrigerated facilities,
grocery operators.
Core Workflow

User uploads:

PDF bills,
scanned invoices,
emailed statements.

Your system:

sends documents to frontier LLM APIs,
extracts structured fields,
compares against history,
identifies anomalies,
generates explanations.
Example Output

“Demand charges increased 27% while total usage remained stable.”

“This fee category did not appear in previous bills.”

“Weekend energy consumption increased significantly.”

What You Actually Build
You SHOULD Build
1. Document ingestion
upload UI
storage
2. Structured normalization layer

Small but important.

Convert LLM output into:

standard schema,
consistent categories,
normalized fields.

This becomes valuable later.

3. Historical comparison engine

This is your real intelligence layer.

Not LLMs.

Compare:

month-over-month,
site-to-site,
fee categories,
usage patterns.
4. Explainability layer

Critical.

Generate:

grounded explanations,
plain-English summaries,
confidence indicators.
5. Lightweight review workflow

User can:

approve,
dismiss,
flag,
annotate anomalies.
What You Should NOT Build

Do NOT build:

vector DBs,
RAG systems,
custom OCR,
training pipelines,
autonomous agents,
complicated orchestration.

These are distractions early.

Architecture Philosophy

Your architecture should initially be:

thin AI layer + strong business logic.

That’s ideal.

Early Tech Stack
Backend

Probably:

Go or Python
PostgreSQL
AI Layer

Use:

Claude,
Gemini,
OpenAI APIs.

Prompt engineering matters more than infra early.

Frontend

Simple dashboard.

Infrastructure

Keep extremely simple.

Success Criteria For Phase 1

You are NOT measuring:

AI sophistication.

You ARE measuring:

usefulness,
anomaly accuracy,
customer interest,
repeated uploads,
money saved,
trust.
PHASE 2 — First Customers & Operational Validation (4–12 Months)
Goal

Get real users before expanding product scope.

This phase is CRITICAL.

Do NOT rush into contract intelligence yet.

What Happens Here

You onboard:

a few paying customers,
pilot customers,
or design partners.

Even 3–5 good customers is huge.

Your Main Goal

Understand:

what anomalies matter,
what gets ignored,
what workflows customers actually want.

This phase shapes the future company.

Most Important Discovery Questions

Examples:

Which anomalies create action?
Which explanations build trust?
What disputes happen repeatedly?
Which vendors are problematic?
What data do customers already have?
What approvals are required?
IMPORTANT

Customers will tell you:

where contract intelligence should enter.

Do NOT guess too early.

PHASE 3 — Utility Contract Intelligence (12–20 Months)
Goal

Expand from:

“billing anomalies”

to:

“billing verification against agreements.”

This is your bridge.

Why This Timing Matters

Now you have:

customers,
real data,
repeated workflows,
known pain patterns.

You’re no longer building blindly.

New Features
Contract upload

Users upload:

utility agreements,
negotiated rate docs,
amendments.
Contract-aware verification

Your system checks:

rates,
discounts,
fee structures,
escalation terms.
Contract drift detection

Detect:

pricing deviations,
unexpected changes,
hidden fees.
IMPORTANT

This is NOT a separate product.

This is:

a new intelligence layer inside the same workflow.

That’s the correct evolution.

PHASE 4 — Multi-Vendor Spend Expansion (20–36 Months)
Goal

Expand beyond utilities.

Now you become:

Spend Integrity Platform.
Expansion Categories

Best next categories:

telecom
SaaS spend
cloud invoices
facilities vendors
waste management

Why?
They resemble utility workflows.

Product Evolution

Now customers can upload:

contracts,
invoices,
renewals,
amendments,
recurring vendor bills.

Your system continuously verifies:

pricing,
usage,
renewals,
deviations.
What Changes Technically?

Surprisingly little initially.

Because your core primitives already exist:

ingestion,
normalization,
comparison,
anomaly detection,
explanation.

That’s why this roadmap is strategically good.

PHASE 5 — Full Contract Drift Platform (3–5 Years)
Goal

Now fully enter:

operational vendor intelligence.
Platform Capabilities

Monitor:

contracts,
invoices,
operational metrics,
SLA behavior,
renewals,
pricing changes.
Example Outputs

“Vendor pricing no longer matches committed discount tier.”

“Telecom invoice contains recurring unexplained surcharge.”

“Cloud spend exceeds contractual usage assumptions.”

What Your Company Becomes

Not:

utility AI,
document AI,
or contract parser.

You become:

a financial operations intelligence company.

That’s much bigger and more defensible.

Final Strategic Advice

Your revised strategy is MUCH better now because:

faster execution,
lower engineering burden,
faster validation,
less infrastructure distraction,
stronger product focus.

The most important thing now is:

don’t overbuild before real customer pull appears.

That’s the biggest risk for technical founders.