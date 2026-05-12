/**
 * Phase 1 ingestion UI: presigned upload (1c) + document list with **processing_error**
 * and status (1h), plus GET detail that includes **latest_raw_extraction** (2a stub).
 *
 * Upload stays disabled until **Organization ID** is filled (``X-Organization-Id``).
 * Prefill via ``VITE_ORG_ID`` in ``frontend/.env``.
 */
import { useCallback, useMemo, useState } from "react";
import {
  completeUpload,
  fetchDocumentDetail,
  fetchDocumentsList,
  presignUpload,
  putFileToPresignedUrl,
  type CompleteUploadResponse,
  type DocumentDetailResponse,
  type DocumentListItemResponse,
} from "./lib/upload";

type Phase = "idle" | "presigning" | "uploading" | "completing" | "done" | "error";
type AppView = "upload" | "documents";

const defaultApiBase = "http://127.0.0.1:8000";

function formatBytes(n: number | null): string {
  if (n === null || n === undefined) {
    return "—";
  }
  if (n < 1024) {
    return `${n} B`;
  }
  if (n < 1024 * 1024) {
    return `${(n / 1024).toFixed(1)} KiB`;
  }
  return `${(n / (1024 * 1024)).toFixed(1)} MiB`;
}

function statusPillClass(status: string): string {
  const base = "status-pill";
  if (status === "failed") {
    return `${base} ${base}--failed`;
  }
  if (status === "extracted") {
    return `${base} ${base}--extracted`;
  }
  return base;
}

export function App() {
  const envApi = import.meta.env.VITE_API_BASE_URL;
  const envOrg = import.meta.env.VITE_ORG_ID;

  const [view, setView] = useState<AppView>("upload");
  const [apiBase, setApiBase] = useState(() => (envApi && envApi.length > 0 ? envApi : defaultApiBase));
  const [orgId, setOrgId] = useState(() => envOrg ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [message, setMessage] = useState("");
  const [uploadPct, setUploadPct] = useState(0);
  const [result, setResult] = useState<CompleteUploadResponse | null>(null);
  const [detail, setDetail] = useState<DocumentDetailResponse | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [docRows, setDocRows] = useState<DocumentListItemResponse[]>([]);
  const [docListLoading, setDocListLoading] = useState(false);
  const [docListError, setDocListError] = useState<string | null>(null);

  const phaseAllowsSubmit = phase === "idle" || phase === "done" || phase === "error";

  const submitBlockedReason = useMemo(() => {
    if (!apiBase.trim()) {
      return "Set API base URL.";
    }
    if (!orgId.trim()) {
      return "Paste your Organization ID (UUID) under Connection — required by the API.";
    }
    if (!file) {
      return "Choose a file.";
    }
    if (!phaseAllowsSubmit) {
      return "Wait for the current step to finish.";
    }
    return null;
  }, [apiBase, orgId, file, phaseAllowsSubmit]);

  const canSubmit = submitBlockedReason === null;

  const runUpload = useCallback(async () => {
    if (!file || !orgId.trim()) {
      setPhase("error");
      setMessage("Choose a file and set Organization ID.");
      return;
    }
    setResult(null);
    setDetail(null);
    setDetailError(null);
    setUploadPct(0);
    try {
      setPhase("presigning");
      setMessage("Requesting presigned upload…");
      const presign = await presignUpload(apiBase.trim(), orgId.trim(), file);

      setPhase("uploading");
      setMessage("Uploading to object storage…");
      await putFileToPresignedUrl(file, presign.upload_url, presign.headers, (loaded, total) => {
        setUploadPct(total > 0 ? Math.round((100 * loaded) / total) : 0);
      });

      setPhase("completing");
      setMessage("Finalizing document (server-side hash)…");
      const done = await completeUpload(apiBase.trim(), orgId.trim(), presign.document_id);
      setResult(done);
      setPhase("done");
      setMessage("Upload complete.");
    } catch (e) {
      setPhase("error");
      setMessage(e instanceof Error ? e.message : String(e));
    }
  }, [apiBase, orgId, file]);

  const loadDetail = useCallback(async () => {
    if (!result || !orgId.trim()) {
      return;
    }
    setDetailError(null);
    setDetail(null);
    try {
      const d = await fetchDocumentDetail(apiBase.trim(), orgId.trim(), result.document_id);
      setDetail(d);
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : String(e));
    }
  }, [apiBase, orgId, result]);

  const loadDocumentList = useCallback(async () => {
    if (!apiBase.trim() || !orgId.trim()) {
      setDocListError("Set API base URL and Organization ID first.");
      return;
    }
    setDocListError(null);
    setDocListLoading(true);
    try {
      const rows = await fetchDocumentsList(apiBase.trim(), orgId.trim(), 200);
      setDocRows(rows);
    } catch (e) {
      setDocListError(e instanceof Error ? e.message : String(e));
      setDocRows([]);
    } finally {
      setDocListLoading(false);
    }
  }, [apiBase, orgId]);

  const goToDocuments = useCallback(() => {
    setView("documents");
    void loadDocumentList();
  }, [loadDocumentList]);

  return (
    <div className={view === "documents" ? "page page--wide" : "page"}>
      <header className="header">
        <nav className="app-nav" aria-label="Primary">
          <button type="button" className={view === "upload" ? "nav-btn nav-btn--active" : "nav-btn"} onClick={() => setView("upload")}>
            Upload
          </button>
          <button type="button" className={view === "documents" ? "nav-btn nav-btn--active" : "nav-btn"} onClick={() => void goToDocuments()}>
            Documents
          </button>
        </nav>
        <h1>{view === "upload" ? "Document upload" : "Ingestion status"}</h1>
        <p className="lede">
          {view === "upload"
            ? "Utility bills and related PDFs — presigned flow (dev)."
            : "Pipeline state per document (upload + email sources). Newest first."}
        </p>
      </header>

      <section className="card">
        <h2>Connection</h2>
        <label className="field">
          <span>API base URL</span>
          <input
            value={apiBase}
            onChange={(e) => setApiBase(e.target.value)}
            placeholder="http://127.0.0.1:8000"
            autoComplete="off"
          />
        </label>
        <label className="field">
          <span>Organization ID (UUID)</span>
          <input
            value={orgId}
            onChange={(e) => setOrgId(e.target.value)}
            placeholder="from Postgres or register-document output"
            spellCheck={false}
            autoComplete="off"
          />
        </label>
        <p className="hint">
          Set <code>VITE_API_BASE_URL</code> and <code>VITE_ORG_ID</code> in <code>frontend/.env</code> to prefill.
        </p>
      </section>

      {view === "upload" ? (
        <>
          <section className="card">
            <h2>File</h2>
            <input
              type="file"
              accept="application/pdf,.pdf"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setPhase("idle");
                setMessage("");
                setResult(null);
                setDetail(null);
              }}
            />
            {file ? (
              <p className="filemeta">
                Selected: <strong>{file.name}</strong> — {(file.size / 1024).toFixed(1)} KiB
              </p>
            ) : null}
            <div className="actions">
              <button
                type="button"
                disabled={!canSubmit}
                title={submitBlockedReason ?? undefined}
                onClick={() => void runUpload()}
              >
                Upload
              </button>
            </div>
            {submitBlockedReason ? <p className="upload-hint">{submitBlockedReason}</p> : null}
            {phase !== "idle" && phase !== "error" ? (
              <div className="progress-wrap" aria-live="polite">
                <div
                  className="progress-bar"
                  style={{
                    width: `${phase === "uploading" ? uploadPct : phase === "done" ? 100 : phase === "completing" ? 92 : 8}%`,
                  }}
                />
                <p className="status">{message}</p>
              </div>
            ) : null}
            {phase === "error" ? <p className="error">{message}</p> : null}
          </section>

          {result ? (
            <section className="card success">
              <h2>Result</h2>
              <dl className="kv">
                <dt>Document ID</dt>
                <dd>
                  <code>{result.document_id}</code>
                </dd>
                <dt>SHA-256</dt>
                <dd>
                  <code>{result.sha256}</code>
                </dd>
                <dt>Size</dt>
                <dd>{result.byte_size} bytes</dd>
                <dt>Status</dt>
                <dd>
                  <span className={statusPillClass(result.processing_status)}>{result.processing_status}</span>
                </dd>
                {result.processing_error ? (
                  <>
                    <dt>Error</dt>
                    <dd className="cell-error-inline">{result.processing_error}</dd>
                  </>
                ) : null}
              </dl>
              <div className="actions-row">
                <button type="button" className="secondary" onClick={() => void loadDetail()}>
                  Load document detail (GET)
                </button>
                <button type="button" className="secondary" onClick={() => void goToDocuments()}>
                  All documents
                </button>
              </div>
              {detail ? <pre className="json">{JSON.stringify(detail, null, 2)}</pre> : null}
              {detailError ? <p className="error">{detailError}</p> : null}
            </section>
          ) : null}
        </>
      ) : (
        <section className="card">
          <div className="doc-list-toolbar">
            <h2>Documents</h2>
            <button type="button" disabled={docListLoading} onClick={() => void loadDocumentList()}>
              {docListLoading ? "Loading…" : "Refresh"}
            </button>
          </div>
          {docListError ? <p className="error">{docListError}</p> : null}
          {!docListError && !docListLoading && docRows.length === 0 ? (
            <p className="hint">No documents yet for this organization.</p>
          ) : null}
          {docRows.length > 0 ? (
            <div className="table-wrap">
              <table className="doc-table">
                <thead>
                  <tr>
                    <th>Created</th>
                    <th>Status</th>
                    <th>Error</th>
                    <th>Source</th>
                    <th>MIME</th>
                    <th>Size</th>
                    <th>Document ID</th>
                  </tr>
                </thead>
                <tbody>
                  {docRows.map((row) => (
                    <tr key={row.document_id}>
                      <td>{new Date(row.created_at).toLocaleString()}</td>
                      <td>
                        <span className={statusPillClass(row.processing_status)}>{row.processing_status}</span>
                      </td>
                      <td className="cell-error" title={row.processing_error ?? undefined}>
                        {row.processing_error ? row.processing_error : "—"}
                      </td>
                      <td>{row.source}</td>
                      <td className="cell-mono">{row.mime_type}</td>
                      <td>{formatBytes(row.byte_size)}</td>
                      <td className="cell-mono cell-id">{row.document_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </section>
      )}
    </div>
  );
}
