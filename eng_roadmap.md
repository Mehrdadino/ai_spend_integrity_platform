# Technical & Engineering Roadmap

**Product:** AI-Powered Spend Integrity Platform  
**Canonical product phases:** [`product_roadmap.md`](product_roadmap.md)  
**Stack anchor:** Python backend  

This document is the engineering counterpart to the product vision. **Product Phase 1 (0–4 months) ends with a functional product:** the full loop **upload / email → extract → normalize → compare → explain → review** works in production for real utility bills—not a partial demo missing ingestion, comparison, or workflow.

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
