/**
 * Admin-only PDF test-bill generator.
 *
 * Lets a platform admin configure batches of synthetic utility bills,
 * generate them as valid PDFs in the browser (no server call), preview
 * each one side-by-side, download individually, or download the batch as one ZIP.
 *
 * Generated PDFs have an embedded text layer so pypdf can extract them
 * without OCR — they are valid input for the full ingestion pipeline.
 */

import { useEffect, useRef, useState } from "react";
import {
  MONTH_OFFSETS,
  PRESETS,
  SCENARIO_LABELS,
  SCENARIO_RULES,
  SCENARIO_SEVERITY,
  generateBillPdf,
  getFilename,
  zipGeneratedPdfs,
  type BillConfig,
  type ScenarioKey,
  type UtilityType,
} from "../lib/pdfGenerator";

// ── Types ─────────────────────────────────────────────────────────────────────

interface GeneratedItem {
  config:   BillConfig;
  blob:     Blob;
  blobUrl:  string;
  filename: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function PdfGeneratorPage() {
  // ── Form state ──
  const [siteName,    setSiteName]    = useState("Site A");
  const [monthOffset, setMonthOffset] = useState(-3);
  const [utility,     setUtility]     = useState<UtilityType>("electricity");
  const [scenario,    setScenario]    = useState<ScenarioKey>("normal");

  // ── Batch state ──
  const [batch, setBatch] = useState<BillConfig[]>([]);

  // ── Generated state ──
  const [generated,   setGenerated]   = useState<GeneratedItem[]>([]);
  const [previewUrl,  setPreviewUrl]  = useState<string | null>(null);
  const [previewIdx,  setPreviewIdx]  = useState<number>(0);
  const [zipping,     setZipping]     = useState(false);
  const generatedRef = useRef<GeneratedItem[]>([]);

  // Revoke all blob URLs on unmount
  useEffect(() => {
    return () => {
      generatedRef.current.forEach(item => URL.revokeObjectURL(item.blobUrl));
    };
  }, []);

  // ── Handlers ──────────────────────────────────────────────────────────────

  function addToBatch() {
    if (!siteName.trim()) return;
    const cfg: BillConfig = {
      id: crypto.randomUUID(),
      siteName: siteName.trim(),
      monthOffset,
      utility,
      scenario,
    };
    setBatch(prev => [...prev, cfg]);
  }

  function removeBatchItem(id: string) {
    setBatch(prev => prev.filter(b => b.id !== id));
  }

  function applyPreset(presetId: string) {
    const preset = PRESETS.find(p => p.id === presetId);
    if (!preset) return;
    const newItems = preset.bills.map(b => ({ ...b, id: crypto.randomUUID() }));
    setBatch(prev => [...prev, ...newItems]);
  }

  function generateAll() {
    if (batch.length === 0) return;
    // Revoke previous blob URLs
    generatedRef.current.forEach(item => URL.revokeObjectURL(item.blobUrl));

    const items: GeneratedItem[] = batch.map(cfg => {
      const blob    = generateBillPdf(cfg);
      const blobUrl = URL.createObjectURL(blob);
      return { config: cfg, blob, blobUrl, filename: getFilename(cfg) };
    });

    generatedRef.current = items;
    setGenerated(items);
    setPreviewIdx(0);
    setPreviewUrl(items[0]?.blobUrl ?? null);
  }

  function selectPreview(idx: number) {
    setPreviewIdx(idx);
    setPreviewUrl(generated[idx]?.blobUrl ?? null);
  }

  /** One ZIP avoids Chrome/Safari blocking more than ~10 rapid automatic downloads. */
  async function downloadAll() {
    if (generated.length === 0 || zipping) return;
    setZipping(true);
    try {
      const zipBlob = await zipGeneratedPdfs(
        generated.map(({ blob, filename }) => ({ blob, filename })),
      );
      const url = URL.createObjectURL(zipBlob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `utility-test-bills-${generated.length}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } finally {
      setZipping(false);
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="pdf-gen-page">

      {/* ── Quick presets ── */}
      <section className="card">
        <h2>Quick presets</h2>
        <p className="card-subtitle">
          Add a pre-configured batch of bills designed to exercise specific comparison rules.
          Presets are <em>additive</em> — click multiple to combine scenarios.
        </p>
        <div className="preset-grid">
          {PRESETS.map(p => (
            <button
              key={p.id}
              type="button"
              className="preset-btn"
              onClick={() => applyPreset(p.id)}
            >
              <span className="preset-btn__label">
                {p.label}
                <span className="preset-btn__count">{p.count} bill{p.count > 1 ? "s" : ""}</span>
              </span>
              <span className="preset-btn__desc">{p.description}</span>
            </button>
          ))}
        </div>
      </section>

      {/* ── Manual configure ── */}
      <section className="card">
        <h2>Configure a bill</h2>
        <p className="card-subtitle">
          Set each option then click <strong>Add to batch</strong>. Repeat for as many bills as you need.
        </p>

        <div className="pdf-gen-form-grid">
          {/* Site label */}
          <label className="field">
            <span>Site label</span>
            <input
              type="text"
              value={siteName}
              maxLength={80}
              placeholder="e.g. Main Street, Warehouse, Site A"
              onChange={e => setSiteName(e.target.value)}
            />
          </label>

          {/* Billing month */}
          <label className="field">
            <span>Billing month</span>
            <select value={monthOffset} onChange={e => setMonthOffset(Number(e.target.value))}>
              {MONTH_OFFSETS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </label>

          {/* Utility type */}
          <div className="field">
            <span className="field-label">Utility type</span>
            <div className="radio-group">
              {(["electricity", "gas", "water", "telecom"] as UtilityType[]).map(u => (
                <label
                  key={u}
                  className={`radio-option${utility === u ? " radio-option--checked" : ""}`}
                >
                  <input
                    type="radio"
                    name="utility"
                    value={u}
                    checked={utility === u}
                    onChange={() => setUtility(u)}
                  />
                  {u.charAt(0).toUpperCase() + u.slice(1)}
                </label>
              ))}
            </div>
          </div>

          {/* Scenario */}
          <label className="field">
            <span>Scenario</span>
            <select value={scenario} onChange={e => setScenario(e.target.value as ScenarioKey)}>
              {(Object.keys(SCENARIO_LABELS) as ScenarioKey[]).map(k => (
                <option key={k} value={k}>{SCENARIO_LABELS[k]}</option>
              ))}
            </select>
          </label>
        </div>

        {/* Scenario description */}
        {SCENARIO_RULES[scenario].length > 0 ? (
          <p className="hint" style={{ marginBottom: "0.85rem" }}>
            <strong>Expected signals:</strong>{" "}
            {SCENARIO_RULES[scenario].join(", ")}
          </p>
        ) : (
          <p className="hint" style={{ marginBottom: "0.85rem" }}>
            No signals expected — use as a baseline / prior bill.
          </p>
        )}

        <button type="button" onClick={addToBatch} disabled={!siteName.trim()}>
          + Add to batch
        </button>
      </section>

      {/* ── Batch list ── */}
      {batch.length > 0 && (
        <section className="card">
          <div className="doc-list-toolbar">
            <h2>Batch — {batch.length} bill{batch.length > 1 ? "s" : ""}</h2>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button type="button" className="secondary" onClick={() => setBatch([])}>
                Clear all
              </button>
              <button type="button" onClick={generateAll}>
                Generate {batch.length} PDF{batch.length > 1 ? "s" : ""}
              </button>
            </div>
          </div>
          <p className="doc-list-lede">
            Table order is for readability only. Assign each PDF to the matching site; upload order
            does not matter when billing period dates are extracted from the bill.
          </p>
          <div className="table-wrap">
            <table className="doc-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Site label</th>
                  <th>Billing month</th>
                  <th>Utility</th>
                  <th>Scenario</th>
                  <th>Expected signals</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {batch.map((cfg, i) => (
                  <tr key={cfg.id}>
                    <td className="cell-mono">{i + 1}</td>
                    <td style={{ fontWeight: 600 }}>{cfg.siteName}</td>
                    <td>{MONTH_OFFSETS.find(o => o.value === cfg.monthOffset)?.label ?? cfg.monthOffset}</td>
                    <td>{cfg.utility.charAt(0).toUpperCase() + cfg.utility.slice(1)}</td>
                    <td>
                      {SCENARIO_SEVERITY[cfg.scenario] !== "none" ? (
                        <span className={`comparison-severity comparison-severity--${SCENARIO_SEVERITY[cfg.scenario]}`}>
                          {SCENARIO_LABELS[cfg.scenario]}
                        </span>
                      ) : (
                        <span className="comparison-severity comparison-severity--info" style={{ opacity: 0.6 }}>
                          {SCENARIO_LABELS[cfg.scenario]}
                        </span>
                      )}
                    </td>
                    <td className="pdf-gen-rules-cell">
                      {SCENARIO_RULES[cfg.scenario].length > 0
                        ? SCENARIO_RULES[cfg.scenario].join(", ")
                        : <span style={{ color: "var(--muted)" }}>—</span>
                      }
                    </td>
                    <td>
                      <button
                        type="button"
                        className="secondary"
                        style={{ padding: "0.2rem 0.55rem", fontSize: "0.75rem" }}
                        onClick={() => removeBatchItem(cfg.id)}
                        aria-label={`Remove bill ${i + 1}`}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* ── Generated PDFs ── */}
      {generated.length > 0 && (
        <section className="card">
          <div className="doc-list-toolbar">
            <h2>Generated — {generated.length} PDF{generated.length > 1 ? "s" : ""}</h2>
            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
              <span className="hint" style={{ margin: 0 }}>
                Click a card to preview · per-PDF links below, or one ZIP for the full batch
              </span>
              <button
                type="button"
                className="secondary"
                onClick={() => void downloadAll()}
                disabled={zipping}
              >
                {zipping ? "Building ZIP…" : `Download all (${generated.length}) as ZIP`}
              </button>
            </div>
          </div>

          <div className="pdf-gen-viewer-layout">
            {/* Large preview */}
            <div className="pdf-gen-main-preview">
              {previewUrl ? (
                <>
                  <div className="pdf-gen-preview-label">
                    <span className="pdf-gen-preview-filename">
                      {generated[previewIdx]?.filename}
                    </span>
                    {generated[previewIdx] && SCENARIO_SEVERITY[generated[previewIdx].config.scenario] !== "none" && (
                      <span className={`comparison-severity comparison-severity--${SCENARIO_SEVERITY[generated[previewIdx].config.scenario]}`}>
                        {SCENARIO_LABELS[generated[previewIdx].config.scenario]}
                      </span>
                    )}
                  </div>
                  <iframe
                    src={previewUrl}
                    title={`Preview: ${generated[previewIdx]?.filename}`}
                    className="pdf-gen-iframe"
                  />
                </>
              ) : (
                <div className="pdf-gen-placeholder">Select a PDF to preview</div>
              )}
            </div>

            {/* Thumbnail sidebar */}
            <div className="pdf-gen-thumb-list">
              {generated.map((item, i) => (
                <div
                  key={item.config.id}
                  className={`pdf-thumb${previewIdx === i ? " pdf-thumb--active" : ""}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => selectPreview(i)}
                  onKeyDown={e => (e.key === "Enter" || e.key === " ") && selectPreview(i)}
                >
                  <div className="pdf-thumb__header">
                    <span className="pdf-thumb__num">#{i + 1}</span>
                    {SCENARIO_SEVERITY[item.config.scenario] !== "none" && (
                      <span
                        className={`comparison-severity comparison-severity--${SCENARIO_SEVERITY[item.config.scenario]}`}
                        style={{ fontSize: "0.68rem", padding: "0.1rem 0.45rem" }}
                      >
                        {SCENARIO_LABELS[item.config.scenario]}
                      </span>
                    )}
                  </div>
                  <span className="pdf-thumb__name">{item.filename}</span>
                  <div className="pdf-thumb__meta">
                    <span>{item.config.siteName}</span>
                    <span>·</span>
                    <span>{MONTH_OFFSETS.find(o => o.value === item.config.monthOffset)?.label}</span>
                  </div>
                  <div className="pdf-thumb__actions">
                    <a
                      href={item.blobUrl}
                      download={item.filename}
                      className="doc-table__link-btn"
                      onClick={e => e.stopPropagation()}
                    >
                      ↓ Download
                    </a>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Upload hint */}
          <div className="pdf-gen-upload-hint">
            <strong>Next step:</strong> go to{" "}
            <strong>Upload</strong>, pick the site that matches each PDF label (Main Street, Warehouse,
            etc.). MoM and new-fee use <strong>billing period dates on the bill</strong>, not upload
            order — these test PDFs include period dates, so you may upload in any sequence. Use{" "}
            <strong>EXTRACTION_LLM_API_KEY</strong> for telecom/domain packs and real line extraction;
            without it, stub lines still trigger extraction-quality signals on text-rich PDFs.
          </div>
        </section>
      )}
    </div>
  );
}
