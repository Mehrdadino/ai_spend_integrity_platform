/**
 * Phase 1 ingestion UI: presigned upload (1c) + document list with **processing_error**
 * and status (1h), plus a **document viewer** (preview + metadata) from list click,
 * upload result, or deep link ``?doc=<uuid>`` (requires ``X-Organization-Id``).
 *
 * Upload stays disabled until **Organization ID** is filled (``X-Organization-Id``).
 * Prefill via ``VITE_ORG_ID`` in ``frontend/.env``.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  completeUpload,
  fetchDocumentViewer,
  fetchDocumentsList,
  presignUpload,
  putFileToPresignedUrl,
  type CompleteUploadResponse,
  type DocumentListItemResponse,
  type DocumentViewerResponse,
} from "./lib/upload";

type Phase = "idle" | "presigning" | "uploading" | "completing" | "done" | "error";
type AppView = "upload" | "documents";

const defaultApiBase = "http://127.0.0.1:8000";

/** Read ``doc`` from the current location (deep link to open the viewer). */
function docIdFromSearch(): string | null {
  const raw = new URLSearchParams(window.location.search).get("doc");
  const id = raw?.trim();
  return id && id.length > 0 ? id : null;
}

/** Set or remove ``?doc=`` without navigation (shareable viewer URL per org in same tab). */
function replaceDocQuery(documentId: string | null): void {
  const url = new URL(window.location.href);
  if (documentId) {
    url.searchParams.set("doc", documentId);
  } else {
    url.searchParams.delete("doc");
  }
  window.history.replaceState(null, "", `${url.pathname}${url.search}`);
}

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

function DocumentPreview({ viewer }: { viewer: DocumentViewerResponse }) {
  const mime = viewer.mime_type;
  if (mime.startsWith("image/")) {
    return <img className="doc-preview-img" src={viewer.read_url} alt="" />;
  }
  if (mime === "application/pdf") {
    return <iframe className="doc-preview-frame" title="Document preview" src={viewer.read_url} />;
  }
  return (
    <p className="hint doc-preview-fallback">
      No embedded preview for this MIME type.{" "}
      <a href={viewer.read_url} target="_blank" rel="noopener noreferrer">
        Open file
      </a>{" "}
      (presigned link expires in {viewer.read_url_expires_in_seconds}s).
    </p>
  );
}

function DocumentViewerPanel({
  viewer,
  loading,
  error,
  onClose,
}: {
  viewer: DocumentViewerResponse | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}) {
  if (!loading && !error && !viewer) {
    return null;
  }
  return (
    <section className="card doc-viewer-card" aria-live="polite">
      <div className="doc-viewer-toolbar">
        <h2>Document</h2>
        <div className="doc-viewer-toolbar-actions">
          {loading ? <span className="hint">Loading preview…</span> : null}
          <button type="button" className="secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {viewer && !loading ? (
        <>
          <div className="doc-preview-shell">
            <DocumentPreview viewer={viewer} />
          </div>
          <dl className="kv doc-viewer-kv">
            <dt>Document ID</dt>
            <dd>
              <code>{viewer.document_id}</code>
            </dd>
            <dt>Organization</dt>
            <dd>
              <code>{viewer.organization_id}</code>
            </dd>
            <dt>Site ID</dt>
            <dd>{viewer.site_id ? <code>{viewer.site_id}</code> : "—"}</dd>
            <dt>Source</dt>
            <dd>{viewer.source}</dd>
            <dt>Status</dt>
            <dd>
              <span className={statusPillClass(viewer.processing_status)}>{viewer.processing_status}</span>
            </dd>
            {viewer.processing_error ? (
              <>
                <dt>Error</dt>
                <dd className="cell-error-inline">{viewer.processing_error}</dd>
              </>
            ) : null}
            <dt>MIME</dt>
            <dd className="cell-mono">{viewer.mime_type}</dd>
            <dt>Size</dt>
            <dd>{formatBytes(viewer.byte_size)}</dd>
            <dt>SHA-256</dt>
            <dd>
              <code>{viewer.sha256 ?? "—"}</code>
            </dd>
            <dt>Storage</dt>
            <dd className="cell-mono">
              {viewer.bucket} / {viewer.object_key}
            </dd>
            <dt>Created</dt>
            <dd>{new Date(viewer.created_at).toLocaleString()}</dd>
          </dl>
          {viewer.latest_raw_extraction ? (
            <details className="doc-viewer-raw">
              <summary>Latest raw extraction (debug)</summary>
              <pre className="json">{JSON.stringify(viewer.latest_raw_extraction, null, 2)}</pre>
            </details>
          ) : null}
        </>
      ) : null}
    </section>
  );
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

  const [docRows, setDocRows] = useState<DocumentListItemResponse[]>([]);
  const [docListLoading, setDocListLoading] = useState(false);
  const [docListError, setDocListError] = useState<string | null>(null);

  /** Which document the viewer should load; kept in sync with ``?doc=`` when user picks a row. */
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [documentViewer, setDocumentViewer] = useState<DocumentViewerResponse | null>(null);
  const [viewerLoading, setViewerLoading] = useState(false);
  const [viewerError, setViewerError] = useState<string | null>(null);

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

  const closeViewer = useCallback(() => {
    setSelectedDocId(null);
    replaceDocQuery(null);
  }, []);

  /** Deep link: open Documents tab and select ``?doc=`` once on first mount. */
  useEffect(() => {
    const id = docIdFromSearch();
    if (!id) {
      return;
    }
    setView("documents");
    setSelectedDocId(id);
  }, []);

  /** Load presigned viewer payload whenever the selected id or org connection changes. */
  useEffect(() => {
    if (!selectedDocId || !orgId.trim() || !apiBase.trim()) {
      setDocumentViewer(null);
      setViewerError(null);
      setViewerLoading(false);
      return;
    }
    let cancelled = false;
    setViewerLoading(true);
    setViewerError(null);
    setDocumentViewer(null);
    void fetchDocumentViewer(apiBase.trim(), orgId.trim(), selectedDocId)
      .then((v) => {
        if (!cancelled) {
          setDocumentViewer(v);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setViewerError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setViewerLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedDocId, orgId, apiBase]);

  const runUpload = useCallback(async () => {
    if (!file || !orgId.trim()) {
      setPhase("error");
      setMessage("Choose a file and set Organization ID.");
      return;
    }
    setResult(null);
    closeViewer();
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
  }, [apiBase, orgId, file, closeViewer]);

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
    setSelectedDocId(docIdFromSearch());
    void loadDocumentList();
  }, [loadDocumentList]);

  const goToUpload = useCallback(() => {
    setView("upload");
    closeViewer();
  }, [closeViewer]);

  const openDocumentInViewer = useCallback((documentId: string) => {
    setSelectedDocId(documentId);
    replaceDocQuery(documentId);
  }, []);

  const pageClass = view === "documents" ? "page page--wide" : "page";
  const pageWideWithViewer = view === "documents" && (selectedDocId !== null || viewerLoading || viewerError);

  return (
    <div className={`${pageClass}${pageWideWithViewer ? " page--viewer" : ""}`}>
      <header className="header">
        <nav className="app-nav" aria-label="Primary">
          <button type="button" className={view === "upload" ? "nav-btn nav-btn--active" : "nav-btn"} onClick={goToUpload}>
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
            : "Pipeline state per document (upload + email sources). Click a row for preview and metadata. Newest first."}
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
          Set <code>VITE_API_BASE_URL</code> and <code>VITE_ORG_ID</code> in <code>frontend/.env</code> to prefill. Open a document with{" "}
          <code>?doc=&lt;uuid&gt;</code> in the URL after choosing this org.
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
                <button type="button" className="secondary" onClick={() => openDocumentInViewer(result.document_id)}>
                  Load preview &amp; detail
                </button>
                <button type="button" className="secondary" onClick={() => void goToDocuments()}>
                  All documents
                </button>
              </div>
              <DocumentViewerPanel
                viewer={documentViewer?.document_id === result.document_id ? documentViewer : null}
                loading={viewerLoading && selectedDocId === result.document_id}
                error={selectedDocId === result.document_id ? viewerError : null}
                onClose={closeViewer}
              />
            </section>
          ) : null}
        </>
      ) : (
        <div className="doc-layout">
          <section className="card doc-layout-list">
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
                      <tr
                        key={row.document_id}
                        className={`doc-table__row${selectedDocId === row.document_id ? " doc-table__row--selected" : ""}`}
                        onClick={() => openDocumentInViewer(row.document_id)}
                        onKeyDown={(ev) => {
                          if (ev.key === "Enter" || ev.key === " ") {
                            ev.preventDefault();
                            openDocumentInViewer(row.document_id);
                          }
                        }}
                        tabIndex={0}
                        role="button"
                        aria-label={`Open document ${row.document_id}`}
                      >
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
            <p className="hint doc-table-hint">Tip: unfinished uploads (no object in storage yet) return 400 from the viewer API until you complete the PUT flow.</p>
          </section>
          <DocumentViewerPanel viewer={documentViewer} loading={viewerLoading} error={viewerError} onClose={closeViewer} />
        </div>
      )}
    </div>
  );
}
