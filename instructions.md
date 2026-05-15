# Bill extraction & comparison — UI guide

Everything below is done in the **web app** (`./scripts/dev.sh` → open http://127.0.0.1:5173). No `curl` or CLI required.

---

## Concepts (30 seconds)

| Term | Meaning |
|------|---------|
| **Organization** | Your tenant (who owns data). Set once under **Connection**. |
| **Site** | A **location** under that org (e.g. “Seattle store”). **Not** the org UUID and **not** parsed from the PDF. |
| **Bill** | Normalized line items after the worker runs. |
| **Prior bills** | Older bills for the **same site** — used for month-over-month comparison (§3a). |

---

## One-time setup

1. Start the stack: `./scripts/dev.sh` (from repo root).
2. Open **http://127.0.0.1:5173**.
3. **Organizations** tab → create or pick your org → click **Use in Connection** (fills Organization ID).
4. **Connection** (on any tab, top card):
   - Confirm **API base URL** is `http://127.0.0.1:8000`.
   - Under **Site (location)**:
     - Enter a name (e.g. `Seattle`) → **Create site**.
     - In **Site for uploads**, select **Seattle**.
5. Leave this org and site selected while you upload all Seattle months.

---

## Upload each month’s bill

1. **Upload** tab.
2. Confirm **Connection** still has your org + **Seattle** (or your site) selected.
3. Choose the PDF → **Upload**.
4. Wait until status is **extracted** (use **Documents** tab; the viewer auto-refreshes).

Repeat for every month. **Use the same organization and the same site** every time.

---

## Fix bills you uploaded *before* sites existed

1. **Documents** tab → click a Seattle bill row.
2. In the viewer, find **Site**:
   - Choose **Seattle** in the dropdown.
   - Click **Save site**.
3. Repeat for each old Seattle document that shows **Site** as “—”.

After two or more Seattle bills share the site and are **extracted**, scroll down in the viewer to **Prior bills (same site)**.

---

## OCR vs LLM (why line items look “sample” or real)

| Step | Needs API key? |
|------|----------------|
| PDF / scan → text (pypdf / Tesseract) | **No** |
| Text → your line items (LLM) | **Yes** — `EXTRACTION_LLM_*` in `backend/.env`, restart `dev.sh` |
| Normalized bill in the UI | Always (may be sample lines without LLM) |

**Gemini (in `backend/.env`, then restart `dev.sh`):**

```bash
EXTRACTION_LLM_API_KEY=your-key
EXTRACTION_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
EXTRACTION_LLM_MODEL=gemini-2.5-flash
```

Then **Reprocess** the document in the viewer.

---

## Pipeline diagram

```text
PDF/image  →  [pypdf / Tesseract]  →  plain text        (no LLM)
plain text →  [LLM or stub]        →  JSON line items   (LLM for real data)
JSON       →  [normalization]      →  bills in UI       (no LLM)
same site  →  [prior bills]       →  history table     (§3a, in viewer)
```

---

## Troubleshooting in the UI

| Symptom | What to do |
|---------|------------|
| **Prior bills** empty | Need **2+** extracted bills on the **same site**; assign site on old uploads. |
| **Site** dropdown empty | **Create site** under Connection → **Refresh sites**. |
| Sample line items (“Electricity delivery (sample)”) | Set LLM env vars, restart dev stack, **Reprocess**. |
| Red **LLM structuring error** | Fix model name / key in `.env` (use `gemini-2.5-flash`, not deprecated `2.0-flash`). |

**Cursor** does not replace `EXTRACTION_LLM_API_KEY` — use Google AI Studio or another provider.
