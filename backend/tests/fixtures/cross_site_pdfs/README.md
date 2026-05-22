# Cross-site comparison test PDFs

Generate files (from `backend/`):

```bash
. .venv/bin/activate && python scripts/generate_cross_site_pdfs.py
```

## Upload order (3 core PDFs, 2 sites)

Use the **Connection** site picker so each file lands on the correct site.

| Order | File | Site | Purpose |
|------:|------|------|---------|
| 1 | `01-upload-first-site-b-mar-normal.pdf` | **Cross-Site Site B** | March peer baseline |
| 2 | `02-upload-second-site-a-feb-normal.pdf` | **Cross-Site Site A** | February prior (same-site history) |
| 3 | `03-upload-last-site-a-mar-rare-fee.pdf` | **Cross-Site Site A** | March anchor with rare fee — **upload last** |

After all three are extracted, open **Anomalies → Refresh** (`POST …/materialize-comparisons`) on the anchor document.

With only two sites, §3c reports **`not_comparable_insufficient_peers`** (production requires **3 other sites** in the same service slice and month).

## Full peer signal (5 PDFs)

Also upload (any order after creating sites C and D):

| File | Site |
|------|------|
| `04-optional-site-c-mar-normal.pdf` | Cross-Site Site C |
| `05-optional-site-d-mar-normal.pdf` | Cross-Site Site D |

Then refresh comparisons again. The anchor (`03-upload-last-…`) should surface **`peer_fee_line_rare`** for the grid modernization surcharge.

## Automated tests

```bash
python -m unittest tests.test_extraction_pdf_spec tests.test_peer_cross_site_suite -v
```

PDFs embed a `BILL_SPEC_V1` block so structuring works **without** `EXTRACTION_LLM_API_KEY`.
