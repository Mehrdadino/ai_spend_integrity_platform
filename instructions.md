# Bill extraction: OCR vs LLM vs “structured bill”

This doc explains what runs without an API key, what needs **`EXTRACTION_LLM_API_KEY`**, and how to configure **Google Gemini** (AI Studio dev key).

---

## Two meanings of “structured bill”

| Meaning | What it is | LLM required? |
|--------|------------|----------------|
| **A. Structured in the database** | Rows in `bills` / `bill_line_items`, typed fields, `GET /api/v1/documents/{id}/bill` | **No** — you always get this after a successful pipeline run |
| **B. Structured from *your* PDF** | Line items that match *your* bill (amounts, labels, kWh, etc.) | **Yes today** (or a future rules/template parser we have not built yet) |

### When we said you don’t need an LLM, we meant:

- The **pipeline and UI** work without a key (upload → worker → **normalized bill shape**).
- **OCR** turns scans into **plain text** without an LLM.

### When we said you need a key, we meant:

- Turning messy bill **text** into **your** line items is a separate, harder step. Right now that step is the **LLM**. Without it, we still fill the tables with a **fixed sample** (“Electricity delivery (sample)”, 142.5 USD, …).

So the wording “structured bill” was easy to misread. More precise:

- You **always** get a normalized bill **(A)**.
- You only get **your bill’s content (B)** with **OCR + LLM** (or later a rules/template parser).

---

## Pipeline (what each step does)

```text
PDF/image  →  [pypdf / Tesseract]  →  long string of text     (no LLM)
long text  →  [LLM or stub]        →  JSON line items       (LLM for real data today)
JSON       →  [normalization]      →  bills + bill_line_items (no LLM)
```

**OCR does not produce line items.** It produces something like:

```text
ACME ELECTRIC  Account 12345  ...  Delivery charge  $142.50  ...
```

Something still has to decide which bits are lines, amounts, and units. That is **structuring/parsing** — Phase 1 uses an LLM for that.

---

## Configure extraction (backend `.env`)

Settings are read from **`backend/.env`** (see `backend/app/config.py`). After editing, **restart** `./scripts/dev.sh` and **reprocess** the document.

### OpenAI (defaults)

```bash
EXTRACTION_LLM_API_KEY=sk-...
# optional overrides:
# EXTRACTION_LLM_BASE_URL=https://api.openai.com/v1
# EXTRACTION_LLM_MODEL=gpt-4o-mini
```

### Google Gemini (AI Studio free dev key)

Use Google’s **OpenAI-compatible** endpoint ([docs](https://ai.google.dev/gemini-api/docs/openai)):

```bash
EXTRACTION_LLM_API_KEY=your-gemini-api-key-here
EXTRACTION_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
EXTRACTION_LLM_MODEL=gemini-2.5-flash
```

Notes:

- **`EXTRACTION_LLM_API_KEY`** — the key from [Google AI Studio](https://aistudio.google.com/apikey) (not your Cursor subscription).
- **`EXTRACTION_LLM_BASE_URL`** — required for Gemini; do not use the OpenAI default.
- **`EXTRACTION_LLM_MODEL`** — use a **current** model id (e.g. `gemini-2.5-flash`). **`gemini-2.0-flash` returns HTTP 404 for new API keys** — update `.env` and restart `dev.sh`. See the [models list](https://ai.google.dev/gemini-api/docs/models) if a name 404s.

### Local Ollama (optional, free)

```bash
EXTRACTION_LLM_API_KEY=ollama
EXTRACTION_LLM_BASE_URL=http://127.0.0.1:11434/v1
EXTRACTION_LLM_MODEL=llama3.2
```

Run `ollama serve` and pull the model first. JSON mode support varies by model.

---

## What to check in the UI

After **reprocess**:

| Field | Meaning |
|-------|---------|
| **Structured via** `deterministic_stub` | No API key (or no bill text); sample line items |
| **Structured via** `llm` | LLM produced line items from extracted/OCR text |
| **Structured via** `deterministic_fallback` | Key was set but the LLM call failed; sample lines + **LLM structuring error** message |
| **PDF text … N chars · method** | Text extraction/OCR ran (independent of LLM) |

**Cursor** does not provide an API key for this worker — use OpenAI, Gemini, Groq, Ollama, etc.

---

## System dependencies (OCR, one-time on macOS)

```bash
brew install tesseract poppler
```

Python deps are installed by `./scripts/dev.sh` (`uv sync` in `backend/`).
