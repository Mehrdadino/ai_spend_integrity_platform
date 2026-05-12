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

## Implementation status (repository) — 2026-05-12

**Why this section:** align the product roadmap with what is already built so future work starts from the correct checkpoint.

### Built so far (Phase 1 — ingestion shell + list UI)

- **Stack in repo:** Python **FastAPI**, **PostgreSQL**, **MinIO** (S3-compatible file storage), **Redis + RQ** for a first background job after upload, **Vite + React + TypeScript** UI under `frontend/`. Docker Compose runs Postgres, MinIO, and Redis locally.
- **Document ingestion:** browser, CLI, or **inbound email webhook** can get a file into **object storage** + **Postgres** (`documents` with hash, size, MIME, `source`, `processing_status`). **Presigned upload** + **upload UI** + **read-back** by id; **email** path via `POST /api/v1/webhooks/inbound-email/{token}` (tenant token on org, optional Mailgun signature / static header).
- **Ingestion status (step 1h):** **`GET /api/v1/documents`** lists org documents (newest first); frontend **Documents** tab shows pipeline status, **`processing_error`** when the worker sets **`failed`**, source, MIME, size, and timestamps. GET detail includes the latest **raw extraction** snapshot when present.
- **Background pipeline:** after upload finalize or email ingest, **RQ** runs **`process_document_pipeline`**: **`queued`** → **`received`** → append-only **`document_raw_extractions`** (stub JSON today, **2a**) → **`extracted`**; failures set **`failed`** + **`processing_error`**.
- **Auth:** development-style **organization UUID header** only; not production multi-tenant auth.

### Still to build for Phase 1 MVP (unchanged intent)

Everything under **“You SHOULD Build”** below that is **not** covered above: **structured normalization** beyond raw JSON (**2b–2d**), **historical comparison**, **explainability**, **review workflow** — plus the “upload → anomaly insight” loop that depends on those layers.

### Recommended next focus (product ↔ eng)

- **Normalize and validate:** **`eng_roadmap.md`** step **2b** (Pydantic on LLM output) then **2c–2d** (canonical codes + `bills` / `bill_line_items`).  
- **Wire a real extractor:** replace the worker **stub** payload in **`document_raw_extractions`** with frontier LLM output (same table shape).

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
email forwarding
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