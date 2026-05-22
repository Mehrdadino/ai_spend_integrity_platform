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

## Implementation status (repository) — 2026-05-21 (invite activation)

**Why this section:** align the product roadmap with what is already built so future work starts from the correct checkpoint.

### Built so far (Phase 1 — ingestion through review)

- **Stack in repo:** Python **FastAPI**, **PostgreSQL**, **MinIO**, **Redis + RQ**, **Vite + React + TypeScript** UI. Docker Compose runs Postgres, MinIO, Redis, and **Mailpit** (local SMTP + inbox at **http://127.0.0.1:8025**) for dev email.
- **Document ingestion:** presigned upload (single or **bulk up to 10 PDFs** per batch on Upload tab) + CLI; optional **display name** on single-file upload; **SHA-256 dedupe** per org (re-upload allowed after soft delete); **Organizations** tab (list/create tenants); **Sites** tab (create/list locations); **Documents** tab with viewer, bill panel, **reprocess**, and **auto-refresh** while the worker runs.
- **Sites & upload context:** sidebar **org + site** selectors; **Sites** tab to create/list locations; assign or change **site** on a document in the viewer (**`PATCH …/site`**). Comparison history is per **site** (location), not per utility type.
- **Background pipeline:** RQ worker loads PDF bytes from S3, extracts **embedded text** (`pypdf`), falls back to **Tesseract OCR** for scan-only PDFs / image MIME types, optionally structures via **LLM** when `EXTRACTION_LLM_API_KEY` is set, validates **`generic-bill-v1`** (**2b**), persists **`document_raw_extractions`** (**2a**), normalizes to **`bills` / `bill_line_items`** (**2c–2d**).
- **Without LLM key:** deterministic sample line items still run for dev/CI; bill summary notes that PDF text was extracted but structuring needs an API key.
- **Auth (P1/P3):** **Login UI** + JWT (**remember this device** = 30 days, else ~12h session); email 2FA when **`SMTP_HOST`** is set; **Account** tab; **forgot/reset password**; password policy; **invite-only registration** in production (`AUTH_ALLOW_REGISTRATION=false`, open in dev via **`dev.sh`**). **`dev.sh`** points SMTP at **Mailpit** so invites and OTPs are delivered locally (inbox **:8025**), not only logged on the API.
- **Org teams (B2B):** **`organization_members`** with per-org roles **`org_admin`** | **`member`** | **`viewer`**; **soft deactivate** (**`POST …/members/{id}/deactivate`**, migration **019**, shows **Deactivated by**); email **invites** (expire after **7 days** → status **Invite expired**); **invite activation**; **Team** table (**`GET …/team`**) for all members (Joined / Invited / Expires columns); org admins invite, roles, deactivate (including other admins if one admin remains); viewers read-only; members upload/review.
- **Platform admin** still sees all orgs; dev **`X-Organization-Id`** when `AUTH_ALLOW_DEV_ORG_HEADER=true`.
- **Production hardening:** Redis **rate limits** (e.g. **3/15min** per email on forgot/register/invite, **5/15min** login, **10/min** per IP); **lockout** after **5** failed sign-ins; security headers; production startup validation.
- **§3a prior bills:** `get_prior_bills_for_bill` + **`GET …/bill/prior-bills`** (same org, same `site_id`; period ordering); prior-bill table in document viewer.
- **§3b + §3d + §4:** **`GET …/bill/comparison`** persists anomalies; rule pack **`comparison-v1.3`** — **single-bill integrity** on every bill (no prior): header vs lines, duplicate lines, high fee/tax share, penalty fees, **missing period dates** (warning), credits vs charges, **extraction-quality** signals from ``bills.summary``, **utility/telecom domain packs** (electric demand without kWh, water/gas missing usage, telecom fee clusters); with history: MoM total and new fee lines **only when both bills have confirmed billing periods** (otherwise **`period_comparison_skipped`** — upload order is not used as a month proxy); **labeled golden cases** in ``backend/tests/comparison_labeled_cases.py`` for rule recall regression; **`GET /api/v1/anomalies`** (+ detail) with **template explanations** and **grounding**; **`POST …/materialize-comparisons`** for inbox **Refresh**.
- **§3e comparison backfill:** After worker upsert, **bounded site-wide** comparison when the bill has a `site_id` (correct priors after mid-timeline insert/delete). **Site change** refreshes the new site (via backfill) and the **previous** site when the bill moved. **Soft delete** triggers site-wide refresh. Keyset walk; cap `SITE_BILL_REFRESH_MAX_BILLS` (default 10,000).
- **§5 review workflow:** `review_status` + **`anomaly_review_events`**; **`POST …/anomalies/{id}/review`**; inbox **Review status** filter; per-row **Actions** (approve / dismiss / flag / reopen) with **§5e notes** and **History**.
- **Anomalies inbox UX:** signals **grouped by bill/document**; optional **display name** on list/API; **Filter by bill** — searchable, paginated **`GET /documents/browse`**; **View bill** on group; row click opens document (text can be highlighted without navigating). **Documents** tab **Signals** link and viewer **View in signals inbox** jump to filtered Anomalies.
- **Document labels & delete:** optional **`display_name`** — set on upload, edit/clear in viewer, **`PATCH …/display-name`**; soft delete **`DELETE …/documents/{id}`** + UI **Delete** (S3 bytes retained until hard delete).
- **Invalid / non-utility uploads:** worker sets **`processing_status=unsupported`** + **`unsupported_reason`** (not **`failed`**); no **`bills`** row or comparison — e.g. random text, LLM fallback/stub on real PDFs, empty lines (**``document_validity``**).

### Still to build for Phase 1 MVP

- **Auth / org (deferred):** SSO (OIDC/SAML), email verification on signup/change-email, revoke-all-sessions, auth audit log, TOTP app 2FA, per-org domain allowlist, seat billing.
- **Real outbound email (deferred):** Today local dev uses **Mailpit** only (invites/OTP/reset appear at **:8025**, not Gmail). Later: wire a transactional provider (**Resend**, **SendGrid**, **SES**, etc.) via existing **`SMTP_*`** env vars so org invites and auth mail reach real inboxes; verify **`SMTP_FROM_EMAIL`**; optional **`dev.sh`** toggle so Mailpit stays default but **`.env`** can override for one-off real-inbox tests (no separate prod deploy required). Invite **activation UI** is shipped; delivery to real inboxes still depends on this SMTP work.
- **§3c** site-to-site comparables (cross-location; not started).
- **Real-bill pilot** — production LLM structuring quality on real PDFs; extend labeled golden set from pilot disputes.
- **P2** — worker retries and upload idempotency hardening.

### Recommended next focus (product ↔ eng)

- **Real-bill pilot** — `EXTRACTION_LLM_API_KEY`, validate normalization on real utility PDFs; grow labeled set from pilot PDFs.
- **§3c** — site-to-site comparables when a pilot needs cross-location views.
- **P2** — worker retries + idempotency.
- **Comparison chain by utility type** — optional split of priors by `spend_domain` / service (today: one chain per site only).

### Possible future work (comparison breadth)

- **§3c — site-to-site comparables** — product spec below (peers + three starter rules). **Not started** in code (see [`eng_roadmap.md`](eng_roadmap.md) §0.0).
- **Prior chain by bill type** — e.g. Seattle electric vs Seattle water on the same site as separate comparison chains (workaround today: separate sites).

---

## Cross-site comparison (§3c) — product spec (draft)

**Status:** Not implemented. Same-site MoM / new-fee (**§3b**, per `site_id`) remains the default on every bill.

### Why this exists (business)

Multi-location operators (grocery, cold storage, property portfolios) sometimes ask:

- “Is **this store** unusual, or did **everyone** get the same rate hike / new fee?”
- “Which sites look like **outliers** for usage or delivery $/unit this month?”

That is **portfolio / peer benchmarking**, not “replace last month at this site.”

### What we will **not** do

| Anti-pattern | Why |
|--------------|-----|
| Compare every new bill to **all** bills at **all** other sites on upload | Wrong units, huge false-positive rate, slow, not how AP reviews a bill |
| Use cross-site as the **only** comparison | Day-to-day work is still **this site vs last month** |
| Infer peers from PDF text alone | Peers come from **org + site + normalized service/unit**, not address strings on the invoice |

### Peer group (comparability gate)

A bill is evaluated against a **peer set**, not the whole org.

**Include another site’s bill in the peer set only when:**

1. Same **organization**.
2. Same **`spend_domain`** (e.g. utility — not utility vs telecom).
3. Same **service slice** — same `spend_kind` and/or `canonical_service_key` (e.g. `utility_electric` only vs other electric accounts).
4. Same **billing period window** — e.g. `period_end` in the same calendar month as the anchor bill (configurable slack ± few days).
5. **Minimum peer count** — at least **3 other sites** with a qualifying bill in that window (pilot-tunable). Fewer → outcome **`not_comparable_insufficient_peers`** (info, no outlier math).

**Optional later (site metadata):** region, climate zone, sq ft band, “similar store” tag — user-defined peer groups override auto peers.

**Outcomes (always explicit):**

- `comparable` — peer math ran; anomalies may be created.
- `not_comparable_insufficient_peers` — not enough sites in the slice.
- `not_comparable_mixed_units` — anchor has usage quantity but peers lack the same `quantity_unit`.
- `not_comparable_wrong_domain` — e.g. water bill in an electric peer request.

### When to run (not on every upload by default)

- **Phase 2 / pilot-driven:** optional rule pack (e.g. `comparison-peer-v1`) run via **`POST …/materialize-comparisons`**, a **scheduled job**, or an org setting — **not** bundled into the hot path for every document worker completion unless a pilot explicitly wants it.
- Reuse normalized rows from **§2d**; no LLM in the compare step.

### Starter rules (ship §3c as these three)

| Rule ID | Question it answers | Fire when | Severity | Evidence to store |
|---------|---------------------|-----------|----------|-------------------|
| **`peer_fee_line_rare`** | “Is this fee **only here**?” | Anchor bill has fee line fingerprint **F**; **≤1** peer bill in the window also has **F**; anchor has **≥2** peers total | `warning` | `fingerprint`, `peer_count`, `peers_with_fee`, `peer_site_ids[]`, `period_window` |
| **`peer_fee_line_widespread`** | “Did **everyone** get this new fee?” | **F** appears on anchor and on **≥80%** of peer bills in the window (portfolio rollout / rate case) | `info` | Same as above + `prevalence_pct` |
| **`peer_usage_or_total_outlier`** | “Is this site high vs **similar** sites?” | Comparable unit exists (e.g. total kWh, $/kWh, bill total for same service); anchor value **> peer p75 × 1.25** or **> 2× peer median** (tune constants); **≥3** peers | `warning` | `metric`, `anchor_value`, `peer_median`, `peer_p75`, `peer_count`, `unit`, `period_window` |

**Not in v1 of §3c (defer):** full “compare anchor to every line at every site”; demand vs usage cross-checks across sites; automatic peer discovery without service/unit gates.

### Example narratives (for §4 templates later)

- **Rare fee:** “Late payment rider appears on this bill but on only 1 of 11 peer electric accounts for March 2026.”
- **Widespread fee:** “Grid modernization surcharge appears on 9 of 10 peer accounts — likely a utility-wide charge, not a single-store error.”
- **Outlier:** “March kWh at this site is 2.1× the peer median for electric accounts in the same month.”

### Relation to same-site rules

| Layer | Scope | Example |
|-------|--------|---------|
| **§3b (shipped)** | One `site_id` timeline | MoM total up 27% vs **last month at this site** |
| **§3c (this spec)** | Peer set within org | MoM up 27% **and** peers flat → local issue; MoM up **and** peers up → utility-wide |

### Engineering guardrails (for `eng_roadmap.md`)

- New module e.g. `peer_pack_v1.py`; separate **`rule_pack_version`** so inbox can filter peer vs site anomalies.
- SQL: “bills for org + period window + service key,” capped (e.g. max 50 peer bills), not cartesian all-documents.
- Unit tests with 4–5 synthetic sites in one org; golden cases like §3b labeled harness.

**Build trigger:** first design partner asks for portfolio-level fee or usage outlier questions; until then, **§3c stays out of the repo**.

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