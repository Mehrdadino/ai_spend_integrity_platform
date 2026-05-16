# Technical & Engineering Roadmap

**Product:** AI-Powered Spend Integrity Platform  
**Canonical product phases:** [`product_roadmap.md`](product_roadmap.md)  
**Stack anchor:** Python backend  

This document is the engineering counterpart to the product vision. **Product Phase 1 (0–4 months) ends with a functional product:** the full loop **upload → extract → normalize → compare → explain → review** works in production for real utility bills—not a partial demo missing ingestion, comparison, or workflow.

---

## 0.0 Implementation status (repository)

**Last updated:** 2026-05-15 (P1/P3 JWT auth + RBAC; §3e keyset site scans)  
**Purpose:** checkpoint so later work continues from the right place (see also [`product_roadmap.md`](product_roadmap.md) implementation section).

### Shipped in this repo

| Area | What exists today |
|------|---------------------|
| **Compose (`docker-compose.yml`)** | Postgres (**host 15432**), MinIO (**9000** / console **9001**), Redis (**6379**). |
| **Backend (`backend/`)** | FastAPI; Alembic **`008_anomalies`** + **`009_anomaly_review`** (`anomalies.review_status`, **`anomaly_review_events`**); ORM + **`app/services/review/`** (transitions); **`app/services/explain/`** (§4 templates). |
| **1a** | S3-compatible storage via **boto3** (MinIO locally); `documents` registry; **`register-document`** CLI. Object key pattern `{organization_id}/{document_id}`. |
| **1b** | Documents API + **`GET/POST /api/v1/organizations`** (dev admin). Tenant = **`X-Organization-Id`** on document routes. |
| **1c** | **`frontend/`** Upload, **Documents**, **Anomalies**, **Organizations** tabs; viewer + normalized bill panel; **reprocess**; pipeline **polling**; **Anomalies** §5 **review status** + **Refresh** (batch **materialize-comparisons** + list reload); §5e **note modal** + **History** (audit events). |
| **1d** | **Redis + RQ** + **`document-worker`** (``SimpleWorker`` on macOS): enqueue after upload / reprocess; after bill upsert **§3e** enqueues comparison backfill on the same ``documents`` queue. |
| **1h** | List + detail + **`processing_error`**; latest raw extraction on detail. |
| **2a** | Worker: S3 bytes → **`pypdf` embedded text** → optional **Tesseract OCR** for scan-only PDFs / images → optional LLM → **`generic-bill-v1`** JSONB. |
| **2b** | Strict Pydantic for **`stub-v1`** and **`generic-bill-v1`** (**``extra=forbid``**). |
| **2c–2d** | Normalization + transactional **`bills` / `bill_line_items`** upsert; **`GET …/bill`**. |
| **3a** | Prior-bill queries: `app/services/comparison/period.py`, `app/repositories/bills.py` (`list_bills_for_site`, `get_prior_bills_for_bill`), **`GET …/bill/prior-bills`**. |
| **3b** | Rule pack v1: `rule_pack_v1.py` (MoM total, new fee lines, header mismatch); **`GET …/bill/comparison`**; UI **Comparison insights**. |
| **3d** | Migration **`008_anomalies`**; **`GET /api/v1/anomalies`** (+ **`GET …/anomalies/{id}`** §4d); replace-on-compare persistence in ``evaluate_document_comparison``; **Anomalies** UI tab. New anomalies default **`review_status=open`** (**009**). |
| **3e** | **Shipped:** RQ backfill after worker upsert + **PATCH …/site**; **010** index ``ix_bills_org_site_period_sort``; SQL prior fetch; backfill targets via ``list_document_ids_newest_through_anchor`` (no 500/2000 prefix cap); site-wide refresh uses keyset pages (``iter_document_ids_for_site_keyset``, configurable ``SITE_BILL_REFRESH_MAX_BILLS``). |
| **P1** | **Shipped:** ``POST /api/v1/auth/login``, ``GET /auth/me``; JWT bearer in ``require_auth_context``; optional dev ``X-Organization-Id``; migration **011_user_auth_rbac**. |
| **P3** | **Shipped:** ``users.role`` admin/member; ``require_admin`` on document delete, site create, ``POST …/materialize-comparisons``; review audit ``actor_user_id`` from JWT. |
| **4b–4d** | Template copy + confidence from ``anomalies.evidence`` — ``build_explainability_v1`` (`app/services/explain/anomaly_v1.py`); nested ``explainability`` on anomaly JSON; UI **Grounding** + **Explanation** columns. |
| **Docs soft delete** | Migration **`007_documents_deleted_at`**; **`DELETE /api/v1/documents/{id}`**; UI **Delete** button (hidden from list). |
| **Dev helpers** | **`seed-dev-org`**; **`document-worker`**; **`scripts/dev.sh`** (API + worker + Vite). |

### Not started (still Phase 1 product scope)

- **§3c:** site-to-site comparables (see **Possible future work** below).
- **Cross-cutting P2, P4–P5:** retries/idempotency, observability, E2E smoke.

### Deferred / optional (see also `product_roadmap.md`)

| ID | Item |
|----|------|
| **2-OPT** | Optional `total_amount` on `generic-bill-v1` `raw_payload` (amount due vs sum-of-lines). |
| **1-OPT** | `site_id` on upload UI (API already accepts it). |
| **2-OPT** | OCR quality hardening (DPI/thresholds, coverage tests). |
| **2e** | Internal raw vs normalized viewer (admin). |
| **4b-OPT** | LLM polish on explanation templates. |
| **1e–1g** | Inbound email ingestion (removed from repo; revisit if product wants it). |
| **P2** | Worker retries + idempotency hardening. |

### Possible future work (breadth / scale)

These are **not** in the current sprint; **§3c** stays out of repo until product asks for cross-site rules.

| ID | Item |
|----|------|
| **§3c** | Site-to-site comparables (only where categories/units align; explicit “not comparable” outcomes). |

### Suggested “resume here” order

1. **§3c** — site-to-site comparables when a pilot needs cross-location views.  
2. **P2 + P4–P5** — retries/idempotency, observability, E2E smoke.  
3. **1-OPT** — ``site_id`` on upload UI; real-bill extraction pilot.

---

## 0. Alignment with `product_roadmap.md`

| Product Phase 1 — “You SHOULD Build” | Engineering meaning (must be working at Phase 1 end) |
|--------------------------------------|--------------------------------------------------------|
| **1. Document ingestion** — upload UI, storage | Web upload + presigned/object pipeline; originals in object storage; metadata in Postgres. |
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

**Shared contract (whole Phase 1):** object storage holds originals; Postgres holds metadata and derived rows; workers advance `processing_status` (or equivalent) so UIs do not care *how* extraction runs.

---

#### 1) Document ingestion

| Step | What ships | Decoupling note |
|------|------------|-----------------|
| **1a — Object storage + `documents` registry** | Bucket(s), `documents` rows with `bucket`/`key`/`sha256`/`mime_type`/`byte_size`, org/site linkage. | No UI; test with CLI/scripts. |
| **1b — Presigned (or server) upload API** | Authenticated endpoint(s) returning upload target + creating `document` in `pending` state. | Callable from curl/Postman before any frontend. |
| **1c — Upload UI** | File picker, upload progress, success/error, link to document detail or list. | Depends on **1b** only; **Documents** tab lists pipeline status (step **1h**). |
| **1d — “Document ready” → job enqueue** | On upload completion, enqueue worker job with `document_id` + idempotency key. | Worker can be a **no-op** that flips status to `queued`/`received` until extraction exists. |
| **1e–1g (deferred)** | Inbound email as an ingestion channel (webhook, tenant resolution, attachment policy). | **Not in this repository** (removed); Phase 1 uses presigned upload + CLI only. Revisit if product wants provider-forwarded mail again. |
| **1h — Ingestion status UI** | List documents, show pipeline state, errors surfaced from worker/API. | **Shipped:** `GET /documents` + UI + **`processing_error`**; **`failed`** status on worker exception. |

---

#### 2) Structured normalization layer

| Step | What ships | Decoupling note |
|------|------------|-----------------|
| **2a — `raw_extraction` persistence** | JSONB (+ `model_id` / `extraction_version` / timestamps); append or version per `document_id`. | **Shipped (stub):** **`document_raw_extractions`** + worker; payload is **validated** (2b) then stored as canonical JSON. |
| **2b — Pydantic validate (no repair)** | Strict schema for “what we accept”; structured validation errors logged and surfaced. | **Shipped:** ``StubRawExtractionPayload`` + ``validate_raw_extraction_payload`` before JSONB insert; unknown ``extraction_version`` fails. Unit tests under ``backend/tests/``. |
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
| **3d — `anomalies` persistence** | **Shipped:** `anomalies` + partial unique indexes; ``GET /api/v1/anomalies``; upsert on ``GET …/bill/comparison`` (delete+insert per ``bill_id`` + ``rule_pack_version``); fee rules expand to per-line rows with ``bill_line_item_id``. | Explainability (**4**) reads these rows + stored metrics. |
| **3e — Re-run / backfill job** | **Shipped:** RQ backfill after worker upsert + site PATCH (``app/services/comparison/backfill.py``); refreshes same-site *newest→anchor* chain + optional full refresh for the previous site when a bill moves. | Without Redis, user must still call ``GET …/bill/comparison`` to populate ``anomalies``. |

---

#### 4) Explainability layer

| Step | What ships | Decoupling note |
|------|------------|-----------------|
| **4a — Metric snapshot on compare** | **Shipped:** numbers live in ``anomalies.evidence`` from §3b/SQL (no separate snapshot table). | Grounds §4 templates without re-querying lines. |
| **4b — Copy generation from metrics** | **Shipped:** `app/services/explain/anomaly_v1.py` templates per ``rule_id``. | LLM polish remains **4b-OPT** in deferred table. |
| **4c — Confidence tiers** | **Shipped:** ``high`` / ``medium`` / ``low`` from evidence completeness + ``reasons[]`` for UX. | Variance/age heuristics can extend later. |
| **4d — API: anomaly + explanation + confidence** | **Shipped:** nested ``explainability`` on list + ``GET /api/v1/anomalies/{id}``. | Powers review UI (**5**). |

---

#### 5) Lightweight review workflow

| Step | What ships | Decoupling note |
|------|------------|-----------------|
| **5a — State machine + transition rules** | **Shipped:** states `open` / `approved` / `dismissed` / `flagged`; `app/services/review/transition.py` + **`POST /api/v1/anomalies/{id}/review`**. | UI in **1c** Anomalies tab. |
| **5b — Audit log** | **Shipped:** append-only **`anomaly_review_events`** (**009**); **`GET /api/v1/anomalies/{id}/review-events`**. | Optional UI later. |
| **5c — Anomaly inbox API** | **Shipped:** list **`review_status`**, **`sort`**, **`order`** on **`GET /api/v1/anomalies`**. | Powers **Anomalies** filter. |
| **5d — Review UI (inbox + detail)** | **Shipped:** inbox table **Review** + **Actions** (approve / dismiss / flag / reopen); row actions call **5a**. | Detail drawer for audit **TBD** (optional). |
| **5e — Annotations / notes** | **Shipped:** optional **note** on **`POST …/review`**; inbox **modal** on Approve/Dismiss/Flag/Reopen; **History** loads **`GET …/review-events`**. |

---

#### Cross-cutting: production readiness (still Phase 1)

These are **not** a separate product pillar but parallel tracks that attach to the steps above:

| Step | What ships |
|------|------------|
| **P1 — Auth + tenant context** | **Shipped:** JWT bearer + ``require_auth_context``; ``seed-dev-user``; dev header optional. |
| **P2 — Retries + idempotency** | Worker retries with backoff; idempotent document hash / job keys. |
| **P3 — Minimal RBAC** | **Shipped:** ``admin`` / ``member``; admin-only delete/site-create/materialize; review ``actor_user_id``. |
| **P4 — Observability** | Structured logs, correlation id per `document_id`, basic metrics on job success/fail. |
| **P5 — E2E smoke** | Scripted path: upload → normalized bill → anomaly → explain → review on a fixed PDF set. |

**Suggested dependency order (logical, not calendar):** **1a→1b→1d**; **1c** / **1h** track UI; **2a→2b→2c→2d** after first worker runs extraction; **3a→3b→3d** once **2d** exists for two+ periods; **4a→4b→4c→4d** after **3d**; **5a→5b→5c→5d→5e** can start as soon as **3d** has stable IDs, with UI polishing when **4d** exists. (Inbound email **1e–1g** is deferred—see table above.)

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

**S3-compatible** storage (S3, GCS, R2, MinIO locally) for PDFs and scans. Postgres stores **metadata + pointers** only (`bucket`, `key`, `sha256`, `mime_type`, `byte_size`).

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

Goal: **One coherent product** matching the product roadmap—multi-site utility bills, reliable upload ingestion, anomalies with grounded explanations, user review—not a sequence of disconnected spikes.

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

1. A user can **upload** a utility PDF and see processing status through completion.  
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
