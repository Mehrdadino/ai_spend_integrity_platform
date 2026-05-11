/**
 * Step 1c — Upload UI: presign → PUT to object storage (with progress) → complete.
 *
 * Upload stays disabled until **Organization ID** is filled (same as ``X-Organization-Id`` on the API).
 * Prefill via ``VITE_ORG_ID`` in ``frontend/.env`` (a real ``organizations.id`` from the DB).
 */
import { useCallback, useMemo, useState } from "react";
import {
  completeUpload,
  fetchDocumentDetail,
  presignUpload,
  putFileToPresignedUrl,
  type CompleteUploadResponse,
  type DocumentDetailResponse,
} from "./lib/upload";

type Phase = "idle" | "presigning" | "uploading" | "completing" | "done" | "error";

const defaultApiBase = "http://127.0.0.1:8000";

export function App() {
  const envApi = import.meta.env.VITE_API_BASE_URL;
  const envOrg = import.meta.env.VITE_ORG_ID;

  const [apiBase, setApiBase] = useState(() => (envApi && envApi.length > 0 ? envApi : defaultApiBase));
  const [orgId, setOrgId] = useState(() => envOrg ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [message, setMessage] = useState("");
  const [uploadPct, setUploadPct] = useState(0);
  const [result, setResult] = useState<CompleteUploadResponse | null>(null);
  const [detail, setDetail] = useState<DocumentDetailResponse | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Allow another upload after success/error without forcing a re-pick of the same file in the picker.
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

  return (
    <div className="page">
      <header className="header">
        <h1>Document upload</h1>
        <p className="lede">Utility bills and related PDFs — presigned flow (dev).</p>
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
            <dd>{result.processing_status}</dd>
          </dl>
          <button type="button" className="secondary" onClick={() => void loadDetail()}>
            Load document detail (GET)
          </button>
          {detail ? (
            <pre className="json">{JSON.stringify(detail, null, 2)}</pre>
          ) : null}
          {detailError ? <p className="error">{detailError}</p> : null}
        </section>
      ) : null}
    </div>
  );
}
