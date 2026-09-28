# Using the web app

Day-to-day flow after the stack is running. Install and sign-in defaults are in the [README](README.md).

Open **http://127.0.0.1:5173**. Sign in (local seed user: `admin@dev.local` / `Dev-Admin-Change1!`). Login codes, invites, and password-reset mail show up in Mailpit at **http://127.0.0.1:8025**.

## Concepts

| Term | Meaning |
| --- | --- |
| **Organization** | Tenant that owns the data. Pick one in the sidebar. |
| **Site** | A location under that organization (for example “Seattle store”). It is not read from the PDF. |
| **Bill** | Normalized line items after the worker finishes. |
| **Prior bills** | Older bills for the **same site**, used for month-over-month comparison. |

## One-time setup

1. Start the stack from the repo root: `./scripts/dev.sh`.
2. Sign in.
3. In the sidebar **Organization** list, select **Dev Organization** (seeded on first run). You can create more on the **Organizations** tab.
4. Open **Sites**, enter a name (for example `Seattle`), and click **Create site**.
5. In the sidebar **Site (location)** list, select that site.
6. Keep that organization and site selected while you upload that location’s bills.

The API base URL defaults to `http://127.0.0.1:8000` on the sign-in screen. You only change it if the API is not on that address.

## Upload each month’s bill

1. Open **Upload**.
2. Confirm the sidebar still has your organization and site.
3. Choose one or more PDFs (up to 10) and click **Upload**.
4. Open **Documents** and wait until status is **extracted**. The list refreshes while the worker runs.

Use the same organization and the same site for every month you want compared together.

## Fix bills uploaded before a site existed

1. **Documents** → open the bill.
2. Set **Site** and save.
3. Repeat for each document that has no site.

After two or more extracted bills share that site, the viewer shows **Prior bills (same site)**.

## OCR vs LLM

| Step | Needs an API key? |
| --- | --- |
| PDF or scan → text (`pypdf` / Tesseract) | No. Scans also need Tesseract and Poppler installed. |
| Text → line items (LLM) | Yes. Set `EXTRACTION_LLM_*` in `backend/.env`, then restart `./scripts/dev.sh`. |
| Normalized bill in the UI | Always. Without a key, line items are sample data. |

Example for Gemini, in `backend/.env` only (this file is gitignored):

```bash
EXTRACTION_LLM_API_KEY=your-key
EXTRACTION_LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
EXTRACTION_LLM_MODEL=gemini-2.5-flash
```

Then **Reprocess** the document in the viewer.

## Pipeline

```text
PDF/image  →  pypdf or Tesseract  →  plain text
plain text →  LLM or sample stub  →  JSON line items
JSON       →  normalization       →  bills in the UI
same site  →  prior bills         →  history and anomalies
```

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| **Prior bills** empty | Need **2+** extracted bills on the **same site**. Assign a site on older uploads. |
| Site list empty | Create one on **Sites**, then pick it in the sidebar. |
| Sample line items (“Electricity delivery (sample)”) | Set the LLM variables, restart the dev stack, **Reprocess**. |
| Red **LLM structuring error** | Check the model name and key in `backend/.env`. Use a current model such as `gemini-2.5-flash`. |
| No invite or reset email | Open Mailpit at http://127.0.0.1:8025. `dev.sh` sends mail there, not to a real inbox. |
