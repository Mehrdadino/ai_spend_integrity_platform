# Technical & Engineering Roadmap

**Product:** AI-Powered Spend Integrity Platform  
**Canonical product phases:** [`product_roadmap.md`](product_roadmap.md)  
**Stack anchor:** Python backend  

This document is the engineering counterpart to the product vision. **Product Phase 1 (0–4 months) ends with a functional product:** the full loop **upload / email → extract → normalize → compare → explain → review** works in production for real utility bills—not a partial demo missing ingestion, comparison, or workflow.

---

## 0.0 Implementation status (repository)

**Last updated:** 2026-05-12  
**Purpose:** checkpoint so later work continues from the right place (see also [`product_roadmap.md`](product_roadmap.md) implementation section).

### Shipped in this repo

| Area | What exists today |
|------|---------------------|
| **Compose (`docker-compose.yml`)** | Postgres (**host 15432**), MinIO (**9000** / console **9001**), Redis (**6379**). |
| **Backend (`backend/`)** | FastAPI; Alembic **`001_initial_schema`**, **`002_presign`**, **`003_ingest_token`** (`organizations.ingest_email_token`). ORM tables live: **`organizations`**, **`users`**, **`sites`**, **`documents`**. *Not yet in DB:* `bills`, `bill_line_items`, `anomalies`, review audit tables from the §2.1 calendar blurb. |
| **1a** | S3-compatible storage via **boto3** (MinIO locally); `documents` registry; **`register-document`** CLI. Object key pattern `{organization_id}/{document_id}`. |
| **1b** | `GET /api/v1/documents` (list, step **1h**), `POST /api/v1/documents/presigned-upload`, `POST /api/v1/documents/{id}/complete-upload`, `GET /api/v1/documents/{id}`. Tenant = header **`X-Organization-Id`** (UUID); not real JWT/session auth (P1). |
| **1c** | **`frontend/`** Vite + React + TypeScript: **Upload** + **Documents** tabs; file picker, progress, presign → PUT → complete; link to list after upload; dev CORS on API; MinIO **`MINIO_API_CORS_ALLOW_ORIGIN`** for browser PUT. |
| **1d** | **Redis + RQ**: after durable upload / email ingest, **`enqueue_document_pipeline_safe`**. **`document-worker`** → **`process_document_pipeline`**: `queued` → **`received`** (no-op until extraction). Statuses in use include **`awaiting_object`**, **`queued`**, **`received`** (+ legacy **`pending`** accepted by worker). |
| **1e–1g** | **`POST /api/v1/webhooks/inbound-email/{ingest_token}`**: multipart/MIME (SendGrid/Mailgun-style), PDF policy, size/count caps; org from token; optional **site** hint in `To` / envelope (`site.<uuid>`); optional Mailgun signature + static header gate (`Settings`). |
| **1h** | **Ingestion list API + UI:** `GET /api/v1/documents?limit=` (newest first); frontend table shows `processing_status`, `source`, MIME, size, `created_at`. Worker/API **error text on rows** not wired yet (future small extension). |
| **Dev helpers** | **`seed-dev-org`**; **`document-worker`**; **`register-document`**; **`scripts/dev.sh`**, **`scripts/bootstrap-backend-venv.sh`**, **`scripts/test-inbound-email-local.sh`**; **`print_dev_ingest_webhook`**. |

### Not started (still Phase 1 product scope)

- **§2–5 pillars:** extraction / normalization, comparison, explainability, review (no code paths yet).  
- **Cross-cutting P1–P5** as separate deliverables: real auth, RBAC hardening, observability package, scripted E2E smoke through full loop.

### Suggested “resume here” order

1. **Core loop start:** **2a** (persist `raw_extraction` JSONB) once you run LLM (or stub) from the worker after **`received`**.  
2. **Optional ingestion polish:** persist and display **pipeline errors** on `documents` for failed jobs (extends **1h**).

---

## 0. Alignment with `product_roadmap.md`

| Product Phase 1 — “You SHOULD Build” | Engineering meaning (must be working at Phase 1 end) |
|--------------------------------------|--------------------------------------------------------|
| **1. Document ingestion** — upload UI, email forwarding, storage | Web upload + presigned/object pipeline; inbound email → same pipeline; originals in object storage; metadata in Postgres. |
| **2. Structured normalization layer** | LLM output validated (e.g. Pydantic) → canonical schema, enums, units; `raw_extraction` (JSONB) + normalized tables. |
| **3. Historical comparison engine** | Code-first (not LLM): MoM, site-to-site, fee categories, usage patterns; anomalies persisted with evidence pointers. |
| **4. Explainability layer** | Grounded copy from computed metrics; plain-English summaries; confidence tiers. |
| **5. Lightweight review workflow** | Approve, dismiss, flag, annotate from the dashboard; audit trail on state changes. |

| Product Phase 1 — “Do NOT Build” | Engineering stance |
|----------------------------------|----------------------|
| Vector DBs, RAG, custom OCR, training pipelines, autonomous agents, complicated orchestration | Out of scope for Phase 1; thin AI + strong business logic only. |

**Product Phase 2 (4–12 months)** is *operational validation*: paying users / design partners, learning what matters—not shipping the core loop for the first time. Engineering after Phase 1 focuses on **reliability, cost controls, observability, security/RBAC, and iteration from feedback**—not on “finishing” features that were deferred from Phase 1.

**Product Phase 3+** (contract intelligence, multi-vendor) is future work; the primitives you build in Phase 1 (ingestion, normalization, comparison, explanation) stay the foundation.

### 0.1 Phase 1 pillars → decoupled steps

Each **product milestone** below is split into **independent engineering steps**. Goal: separate PRs/trackers, clear contracts (usually: `document_id` → pipeline status; `bill_id` / `site_id` + period for downstream), and parallel work where dependencies allow.

**Shared contract (whole Phase 1):** object storage holds originals; Postgres holds metadata and derived rows; workers advance `processing_status` (or equivalent) so UIs and email paths do not care *how* extraction runs.

---

#### 1) Document ingestion

| Step | What ships | Decoupling note |
|------|------------|-----------------|
| **1a — Object storage + `documents` registry** | Bucket(s), `documents` rows with `bucket`/`key`/`sha256`/`mime_type`/`byte_size`, org/site linkage. | No UI, no email; test with CLI/scripts. |
| **1b — Presigned (or server) upload API** | Authenticated endpoint(s) returning upload target + creating `document` in `pending` state. | Callable from curl/Postman before any frontend. |
| **1c — Upload UI** | File picker, upload progress, success/error, link to document detail or list. | Depends on **1b** only; **Documents** tab lists pipeline status (step **1h**). |
| **1d — “Document ready” → job enqueue** | On upload completion (and later on email completion), enqueue worker job with `document_id` + idempotency key. | Worker can be a **no-op** that flips status to `queued`/`received` until extraction exists. |
| **1e — Inbound email webhook** | HTTP handler for provider (SendGrid/Mailgun/SES); verify signature; parse MIME. | Same persistence shape as **1a**; no comparison logic. |
| **1f — Email → tenant + site resolution** | Map recipient address, token, or header to `organization_id` / optional `site_id`; reject unknown senders safely. | Can ship after **1e** stores “unresolved” rows if you need a spike first. |
| **1g — Attachment selection + virus/size policy** | Which part becomes `document` (first PDF, largest attachment, etc.); limits and logging. | Keeps **1e** small; rules are config, not ML. |
| **1h — Ingestion status UI** | List documents, show pipeline state, errors surfaced from worker/API. | **Shipped (thin):** `GET /documents` + frontend table; worker error strings on rows still TBD. |

---

#### 2) Structured normalization layer

| Step | What ships | Decoupling note |
|------|------------|-----------------|
| **2a — `raw_extraction` persistence** | JSONB (+ `model_id` / `extraction_version` / timestamps); append or version per `document_id`. | No Pydantic yet; store LLM output as-is for debugging. |
| **2b — Pydantic (or equivalent) validate + repair path** | Strict schema for “what we accept”; structured validation errors logged and surfaced. | Unit-testable without DB; swap models without changing DB shape. |
| **2c — Canonical enums + unit normalization** | Pure functions: categories, units, demand vs energy, tax/fee tags → canonical codes. | No new tables required if you only emit a normalized JSON blob first. |
| **2d — Relational write: `bills` + `bill_line_items`** | Transactional upsert from normalized structure; idempotent re-run on same document. | Comparison (**3**) reads from here, not from raw JSON. |
| **2e — (Optional) Internal raw vs normalized viewer** | Admin-only page or API for support; speeds pilot iteration. | Not required for MVP demo if logs suffice. |

---

#### 3) Historical comparison engine

| Step | What ships | Decoupling note |
|------|------------|-----------------|
| **3a — “Prior bill for site + period” queries** | Repository functions / SQL; define “period” and ordering rules. | No anomaly rows yet; used by tests and **3b**. |
| **3b — Rule pack v1 (code-first)** | MoM deltas, new fee lines, simple thresholds; deterministic outputs + evidence structs. | Table-driven rules file is fine; no LLM. |
| **3c — Site-to-site comparables** | Only where categories/units align; explicit “not comparable” outcomes. | Can ship after **3b** if you gate on schema flags. |
| **3d — `anomalies` persistence** | Insert/update anomalies with pointers to `bill_line_item_id`s or metric keys; dedupe on `(site_id, type, period, fingerprint)`. | Explainability (**4**) reads these rows + stored metrics. |
| **3e — Re-run / backfill job** | When a new bill lands, re-evaluate open windows (e.g. last N periods). | Isolated worker task; decouples from upload path latency. |

---

#### 4) Explainability layer

| Step | What ships | Decoupling note |
|------|------------|-----------------|
| **4a — Metric snapshot on compare** | Persist the numbers used in rules next to each anomaly (or in JSONB evidence). | Makes explanations **grounded** without re-querying fragile joins. |
| **4b — Copy generation from metrics** | Templates / string builders from **4a**; optional LLM “polish” behind a flag. | Ship **4b** with templates only first; LLM is optional. |
| **4c — Confidence tiers** | Heuristics from completeness, variance, data age; stable enum for UI. | Independent module; golden-file tests. |
| **4d — API: anomaly + explanation + confidence** | Single read model for dashboard/inbox. | Review UI (**5**) can mock this until **5** is built. |

---

#### 5) Lightweight review workflow

| Step | What ships | Decoupling note |
|------|------------|-----------------|
| **5a — State machine + transition rules** | States: e.g. `open` / `approved` / `dismissed` / `flagged`; valid transitions only. | API-first; Postman/curl before UI. |
| **5b — Audit log** | Append-only `anomaly_review_events` (who, when, from→to, note). | RLS/tenant filters later; schema early. |
| **5c — Anomaly inbox API** | List/filter/sort by site, period, severity, status. | Powers UI; can return mock explanations until **4d** is live. |
| **5d — Review UI (inbox + detail)** | Table + detail drawer; action buttons call **5a**. | Depends on **5c**; can ship read-only inbox before write actions. |
| **5e — Annotations / notes** | Free-text or structured note on transition. | Small addition after **5a**–**5d** happy path. |

---

#### Cross-cutting: production readiness (still Phase 1)

These are **not** a separate product pillar but parallel tracks that attach to the steps above:

| Step | What ships |
|------|------------|
| **P1 — Auth + tenant context** | Org-scoped JWT/session; middleware injects `organization_id` for all handlers. |
| **P2 — Retries + idempotency** | Worker retries with backoff; idempotent document hash / job keys. |
| **P3 — Minimal RBAC** | e.g. org admin vs member; enforced on review transitions if needed. |
| **P4 — Observability** | Structured logs, correlation id per `document_id`, basic metrics on job success/fail. |
| **P5 — E2E smoke** | Scripted path: upload → normalized bill → anomaly → explain → review on a fixed PDF set. |

**Suggested dependency order (logical, not calendar):** **1a→1b→1d** and **1e→1f→1g→1d** in parallel after **1a**; **1c** / **1h** track UI; **2a→2b→2c→2d** after first worker runs extraction; **3a→3b→3d** once **2d** exists for two+ periods; **4a→4b→4c→4d** after **3d**; **5a→5b→5c→5d→5e** can start as soon as **3d** has stable IDs, with UI polishing when **4d** exists.

---

## 1. Technology decisions

### 1.1 Backend language

| Choice | Rationale |
|--------|-----------|
| **Python 3.12+** | Fast integration with LLM SDKs, solid PDF/text ecosystem, easy iteration for MVP. |

**Framework:** **FastAPI** — async-friendly I/O, OpenAPI, type hints.

### 1.2 System of record: PostgreSQL (not a generic KV store as primary)

**PostgreSQL 16+** is the **source of truth** for organizations, users, sites, documents, bills, line items, anomalies, review actions, and audit history.

- **Relational core:** org → sites → bills → line items → anomalies → decisions.  
- **Read-heavy history + write bursts:** index `(site_id, bill_period_start)` (and similar); connection pooling; later read replicas / partitioning.  
- **Evolving LLM shapes:** **JSONB** for raw or partial extractions; promote stable fields to typed columns.  
- **Scale (years):** partitioning, PgBouncer, replicas; optional Citus if needed—same SQL model.

**Redis (or similar):** optional for rate limits, sessions, idempotency keys, queue broker—not the ledger for spend data.

### 1.3 Object storage

**S3-compatible** storage (S3, GCS, R2, MinIO locally) for PDFs, scans, email attachments. Postgres stores **metadata + pointers** only (`bucket`, `key`, `sha256`, `mime_type`, `byte_size`).

### 1.4 AI layer

Claude, Gemini, OpenAI behind a **small provider abstraction**; structured outputs validated server-side; persist `prompt_id`, `model_id`, `extraction_version` for reproducibility.

### 1.5 Async work

**Background workers** (RQ, Celery, or Dramatiq) for `ingest → extract → normalize → compare → persist anomalies` so HTTP is not blocked on LLM latency. Single pipeline type is enough for Phase 1—avoid heavy orchestration platforms.

### 1.6 Frontend

**React + TypeScript** (Vite) or **Next.js** for a **simple dashboard**: upload, bill list, anomaly inbox, review actions. Auth when you need multi-tenant pilots: magic link or OAuth (Clerk / Auth0 / WorkOS).

### 1.7 Infrastructure (Phase 1)

One Postgres, one object store, one worker deployment, single region. Docker Compose locally; managed Postgres in staging/production. **No** vector DB, RAG, or custom OCR stack in Phase 1.

---

## 2. Engineering roadmap by product phase

### 2.1 Phase 1 (0–4 months) — Functional MVP (everything works)

Goal: **One coherent product** matching the product roadmap—multi-site utility bills, upload + email, anomalies with grounded explanations, user review—not a sequence of disconnected spikes.

Suggested **calendar** (adjust for team size; parallelize where possible):

| Window | Milestone | Outcome |
|--------|-----------|---------|
| **Weeks 1–3** | **Foundation + ingestion shell** | Postgres schema (`organizations`, `users`, `sites`, `documents`, `bills`, `bill_line_items`, `anomalies`, `anomaly_reviews` / audit); object storage + presigned uploads; FastAPI health/logging; **upload UI** creates `document` + file in bucket; job enqueue. |
| **Weeks 2–5** | **Email ingestion** | Inbound provider webhook (SendGrid / Mailgun / SES) → normalize to same `document` + pipeline as UI; idempotency by hash + tenant. |
| **Weeks 4–8** | **Extraction + normalization** | LLM path for PDF/scanned bills; Pydantic validation; normalization to standard categories and units (demand vs energy, fees, taxes); persist raw + normalized. Target **1–2 utility shapes** well, not perfect coverage everywhere. |
| **Weeks 6–10** | **Comparison engine** | Deterministic rules + simple statistics: MoM deltas, new fee lines, usage vs demand inconsistencies, **site-to-site** where comparable; optional time-of-use / “pattern” signals **only when** normalized data supports them (e.g. weekend vs weekday if present). |
| **Weeks 8–11** | **Explainability** | Explanations generated from **stored metrics** (e.g. “Demand charges +27% vs prior period; total kWh within 2%”); confidence from completeness / variance heuristics. |
| **Weeks 9–13** | **Review workflow + dashboard integration** | States: approve, dismiss, flag; notes/annotations; full UI wired to API; audit log on transitions. |
| **Weeks 11–16** | **Integration + production readiness (still Phase 1)** | End-to-end testing on real PDFs; retries/backoff on LLM; basic per-org cost/rate limits; minimal RBAC (e.g. org admin vs member); structured logs + error visibility so you can support pilots. **Phase 1 is not “done” until this runs reliably for repeated uploads.** |

**Phase 1 engineering definition of done (must all be true):**

1. A user can **upload** a utility PDF **or** have it arrive by **email**, and see processing status through completion.  
2. **Normalized** bill data is queryable per site and period.  
3. **Anomalies** appear when history allows (including after the second bill for a site).  
4. Each anomaly has a **grounded explanation** and a **confidence** indicator.  
5. Users can **approve / dismiss / flag / annotate** from the UI; actions persist with audit.  
6. The system tolerates **repeated uploads** and transient LLM failures without corrupting state.

Anything listed above that slips past month 4 is **scope risk**, not “Phase 2 core”—Phase 2 is for learning from customers on top of this baseline.

### 2.2 Phase 2 (4–12 months) — First customers & operational validation (engineering)

Aligned with product roadmap: **no contract-intelligence build** yet; focus on what pilots need.

- Instrument product discovery: which anomaly types are acted on, dismissed, or disputed (events + analytics).  
- Improve **accuracy** on messy real-world formats using labeled sets from customers—not new infra categories.  
- Hardening: observability (OpenTelemetry, dashboards), queue SLOs, backup/restore drills, data retention/deletion per org.  
- Security posture: RLS or strict tenant guards, secrets rotation, optional SSO.  
- Workflow tweaks from design partners (exports, notifications, roles)—still within **utility bill intelligence**.

### 2.3 Phase 3+ (engineering preview)

- **Phase 3:** Contract upload + contract-aware checks layered on the same ingestion, normalization, comparison, and explanation primitives (`product_roadmap.md` Phase 3).  
- **Phase 4–5:** Additional document types and vendors; same core pipeline, expanded schemas and rules.

---

## 3. Data model notes (read/write and scaling)

| Concern | Approach |
|---------|----------|
| **Read-heavy history** | Indexes on `(site_id, bill_period_start)`; materialized views later if dashboards need them. |
| **Write bursts** | Batch line items; one transaction per completed bill. |
| **Large JSON** | JSONB caps; huge blobs in object storage. |
| **Multi-tenant isolation** | `organization_id` everywhere; Postgres RLS when enforcing boundaries in one cluster. |
| **Years-out scale** | Partitioning, replicas, optional Citus; object storage pattern unchanged. |

---

## 4. Phase 1 engineering non-goals

- Vector DB / RAG “semantic search” over bills.  
- Custom OCR model training.  
- Autonomous multi-step agents without human review.  
- Multi-region active-active.  
- Heavy workflow engines (Temporal, etc.) **until** pipelines justify them.

---

## 5. Success metrics

**Phase 1 (product-aligned):** usefulness, anomaly accuracy on a small labeled set, repeated successful uploads, trust (qualitative in pilots)—supported by engineering metrics: end-to-end success rate, p95 processing time, cost per bill, extraction version drift.

**Phase 2:** same metrics segmented by customer; funnel from anomaly → reviewed → action.

---

## 6. One-line stack summary

**Python (FastAPI) + PostgreSQL (JSONB where needed) + S3-compatible object storage + background workers + frontier LLM APIs + simple React dashboard**, with Redis optional for queue/cache—not as the primary transactional store.

**Phase 1 delivers a working product** per `product_roadmap.md`; **Phase 2** makes it safe and instructive to run with real customers.
