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

## Implementation status (repository) — 2026-05-15 (P1/P3 auth + §3e scale)

**Why this section:** align the product roadmap with what is already built so future work starts from the correct checkpoint.

### Built so far (Phase 1 — ingestion + normalization shell)

- **Stack in repo:** Python **FastAPI**, **PostgreSQL**, **MinIO**, **Redis + RQ**, **Vite + React + TypeScript** UI. Docker Compose runs Postgres, MinIO, and Redis locally.
- **Document ingestion:** presigned upload + CLI; **Organizations** tab (list/create tenants); **Documents** tab with viewer, bill panel, **reprocess**, and **auto-refresh** while the worker runs. **Anomalies** tab lists persisted comparison signals (**§3d**).
- **Background pipeline:** RQ worker loads PDF bytes from S3, extracts **embedded text** (`pypdf`), falls back to **Tesseract OCR** for scan-only PDFs / image MIME types, optionally structures via **LLM** when `EXTRACTION_LLM_API_KEY` is set, validates **`generic-bill-v1`** (**2b**), persists **`document_raw_extractions`** (**2a**), normalizes to **`bills` / `bill_line_items`** (**2c–2d**).
- **Without LLM key:** deterministic sample line items still run for dev/CI; bill summary notes that PDF text was extracted but structuring needs an API key.
- **Auth (P1/P3):** JWT login (`POST /api/v1/auth/login`, `GET /auth/me`); org-scoped bearer on document/anomaly/site routes; **admin** vs **member** RBAC (admin: delete document, create site, batch materialize; member: upload/review/read). Dev **`X-Organization-Id`** still accepted when `AUTH_ALLOW_DEV_ORG_HEADER=true`. Seed users via **`seed-dev-user`**.
- **§3a prior bills:** `list_bills_for_site` / `get_prior_bills_for_bill` + **`GET /api/v1/documents/{id}/bill/prior-bills`** (same-org, same-`site_id`; period ordering in eng **3a**).
- **§3b + §3d + §4:** **`GET …/bill/comparison`** persists anomalies; **`GET /api/v1/anomalies`** returns **template explanations** + **grounding tiers** from saved evidence; **`GET …/anomalies/{id}`** for detail; **`POST /api/v1/anomalies/materialize-comparisons`** runs the same comparison for every finished document in the org (optional site filter) so the **Anomalies** tab **Refresh** can populate the list **without opening each document**.
- **§5 review workflow:** Alembic **`009_anomaly_review`** adds **`review_status`** + audit **`anomaly_review_events`**; **`POST /api/v1/anomalies/{id}/review`** transitions state; inbox **Review status** filter and per-row **Actions** (approve / dismiss / flag / reopen) with optional **§5e notes** (modal + **History** audit list).
- **§3e comparison backfill:** After the worker materializes a normalized bill, an RQ job runs the same comparison path as **`GET …/bill/comparison`** for the document (and same-site neighbors when priors can shift). Changing a document’s **site** triggers backfill plus a refresh pass for bills left on the **previous** site (when applicable). Prior-bill queries use an indexed SQL path (default **500** bills/site scan for backfill; immediate priors without loading the full chain).
- **Document soft delete:** `deleted_at` + **`DELETE /api/v1/documents/{id}`** + UI **Delete** (hard delete / purge later).

### Still to build for Phase 1 MVP

**Remaining comparison breadth** (**§3c** is scoped as future work — see below) and hardening on **real** structured bills (template §4 is shipped; optional LLM wording polish can follow).

### Recommended next focus (product ↔ eng)

- **§3c** — site-to-site comparables when pilots need cross-location views.
- **P2** — worker retries + upload idempotency hardening.
- **Real-bill pilot** — `EXTRACTION_LLM_API_KEY`, `site_id` on upload UI (**1-OPT**).

### Possible future work (comparison breadth)

- **§3c — site-to-site comparables:** compare normalized usage/charges across locations when categories and units align, with explicit “not comparable” outcomes. **Not started**; ship only when a pilot needs cross-location views (see [`eng_roadmap.md`](eng_roadmap.md) §0.0).

### Deferred / optional (later — not blocking MVP demo)

Pick these up when a pilot or ops need pushes them; they are intentionally out of the current sprint.

| Item | Why defer |
|------|-----------|
| **`total_amount` on `raw_payload`** | Normalized total is sum-of-lines today; add when we need “amount due” vs line-sum integrity checks. |
| **`site_id` on upload UI** | API/DB already support `site_id`; wire the picker when comparing bills per location matters for users. |
| **OCR quality hardening** | Tune DPI/thresholds, rendering, and scan coverage tests when scan-heavy bills fail extraction. |
| **§3c site-to-site comparables** | See **Possible future work** above; eng step **3c** not implemented. |
| **§3e at extreme scale** | Keyset scans beyond **2000** bills per site if a pilot outgrows current caps. |
| **§2e internal raw vs normalized viewer** | Support/debug tool beyond the current debug JSON panel. |
| **§4b LLM “polish” on explanations** | Ship **§4** with templates first; LLM optional behind a flag. |
| **Inbound email ingestion (eng 1e–1g)** | Presigned upload + CLI is enough for Phase 1. |
| **P2 retries / idempotency** | Track in eng roadmap; not started. |

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