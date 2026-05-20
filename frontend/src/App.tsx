/**
 * Phase 1 ingestion UI: presigned upload, document list, anomaly inbox (§5 review actions), viewer (bill + comparison).
 * Visual design: glass nav, gradient chrome, high-legibility type (Plus Jakarta Sans).
 */
import {
  Fragment,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { AnomalyDocumentFilter } from "./components/AnomalyDocumentFilter";
import { AccountPage } from "./AccountPage";
import { OrganizationTeamPanel } from "./components/OrganizationTeamPanel";
import { PdfGeneratorPage } from "./components/PdfGeneratorPage";
import { formatMoney } from "./lib/format";
import { LoginPage } from "./LoginPage";
import {
  clearSession,
  getStoredUser,
  isPlatformAdmin,
  type AuthUser,
} from "./lib/auth";
import {
  acceptOrganizationInvite,
  canWriteOrgRole,
  isOrgAdminRole,
} from "./lib/organizationTeam";
import {
  createOrganization,
  fetchOrganizationsList,
  type OrganizationResponse,
} from "./lib/organizations";
import { getSelectableTableRowProps } from "./lib/tableRowActivation";
import { createSite, fetchSitesList, type SiteResponse } from "./lib/sites";
import {
  completeUpload,
  deleteDocument,
  fetchAnomaliesList,
  fetchAnomalyReviewEvents,
  fetchDocumentBill,
  fetchDocumentComparison,
  fetchDocumentPriorBills,
  fetchDocumentViewer,
  fetchDocumentsList,
  patchDocumentDisplayName,
  patchDocumentSite,
  postAnomalyReview,
  postMaterializeAnomalyComparisons,
  presignUpload,
  putFileToPresignedUrl,
  reprocessDocument,
  UNSUPPORTED_REPROCESS_MAY_HELP_CODES,
  type AnomalyReviewStatus,
  type BillResponse,
  type CompleteUploadResponse,
  type DocumentListItemResponse,
  type AnomalyResponse,
  type AnomalyReviewEventResponse,
  type DocumentComparisonResponse,
  type DocumentPriorBillsResponse,
  type DocumentViewerResponse,
} from "./lib/upload";

type Phase = "idle" | "presigning" | "uploading" | "completing" | "done" | "error";
type AppView = "upload" | "documents" | "anomalies" | "organizations" | "account" | "pdf-generator";

const defaultApiBase = "http://127.0.0.1:8000";

/** Interval (ms) for refetching viewer + bill while ``queued`` / ``pending`` / ``received``. */
const PIPELINE_POLL_MS = 2500;
const SITE_BY_ORG_STORAGE_KEY = "spend_site_by_org";

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value.trim());
}

function loadStoredSiteId(orgId: string): string {
  try {
    const raw = localStorage.getItem(SITE_BY_ORG_STORAGE_KEY);
    if (!raw) {
      return "";
    }
    const map = JSON.parse(raw) as Record<string, string>;
    return map[orgId] ?? "";
  } catch {
    return "";
  }
}

/** Billing period label + sort key (matches backend §3a ``effective_period_end``). */
function billPeriodSortKey(bill: BillResponse): string {
  if (bill.period_end) {
    return bill.period_end;
  }
  if (bill.period_start) {
    return bill.period_start;
  }
  return bill.created_at.slice(0, 10);
}

function formatBillPeriod(bill: BillResponse): string {
  if (bill.period_start && bill.period_end) {
    return `${bill.period_start} – ${bill.period_end}`;
  }
  if (bill.period_end) {
    return bill.period_end;
  }
  if (bill.period_start) {
    return bill.period_start;
  }
  return `— (uploaded ${new Date(bill.created_at).toLocaleDateString()})`;
}

function priorBillsSortedByPeriod(bills: BillResponse[]): BillResponse[] {
  return [...bills].sort((a, b) => billPeriodSortKey(b).localeCompare(billPeriodSortKey(a)));
}

/** Whether comparison findings are only informational (baseline / setup), not warnings. */
function comparisonIsInfoOnly(comparison: DocumentComparisonResponse | null | undefined): boolean {
  return (
    comparison != null &&
    comparison.findings.length > 0 &&
    comparison.findings.every((f) => f.severity === "info")
  );
}

function comparisonHasNoPriorBill(comparison: DocumentComparisonResponse | null | undefined): boolean {
  return comparison?.findings.some((f) => f.rule_id === "no_prior_bill") ?? false;
}

/** Plain-language label for comparison rule severity (§3b UI). */
function comparisonSeverityLabel(severity: string): string {
  switch (severity) {
    case "info":
      return "Note";
    case "warning":
      return "Heads up";
    case "critical":
      return "Needs attention";
    default:
      return severity;
  }
}

/** Confidence tier label for §4 anomaly inbox (heuristic grounding, not stats). */
function explainConfidenceLabel(tier: string): string {
  switch (tier) {
    case "high":
      return "Grounding: high";
    case "medium":
      return "Grounding: medium";
    case "low":
      return "Grounding: low";
    default:
      return tier;
  }
}

/** Label for grouping anomalies by document (name or short id). */
function anomalyDocumentLabel(parts: {
  document_id: string;
  display_name?: string | null;
}): string {
  const name = parts.display_name?.trim();
  if (name) {
    return name;
  }
  return `Bill ${parts.document_id.slice(0, 8)}…`;
}

type AnomalyDocumentGroup = {
  document_id: string;
  display_name: string | null;
  site_name: string | null;
  site_id: string | null;
  anomalies: AnomalyResponse[];
  latest_at: string;
};

const ANOMALY_REVIEW_PRIORITY: Record<AnomalyReviewStatus, number> = {
  flagged: 4,
  open: 3,
  dismissed: 2,
  approved: 1,
};

function rollupAnomalyReviewStatus(statuses: AnomalyReviewStatus[]): AnomalyReviewStatus | null {
  if (statuses.length === 0) {
    return null;
  }
  return statuses.reduce((best, s) =>
    ANOMALY_REVIEW_PRIORITY[s] > ANOMALY_REVIEW_PRIORITY[best] ? s : best,
  );
}

function groupAnomaliesByDocument(rows: AnomalyResponse[]): AnomalyDocumentGroup[] {
  const byDoc = new Map<string, AnomalyResponse[]>();
  for (const row of rows) {
    const bucket = byDoc.get(row.document_id) ?? [];
    bucket.push(row);
    byDoc.set(row.document_id, bucket);
  }
  const groups: AnomalyDocumentGroup[] = [];
  for (const [document_id, anomalies] of byDoc) {
    anomalies.sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    );
    const display_name =
      anomalies.map((a) => a.document_display_name?.trim()).find(Boolean) ?? null;
    const head = anomalies[0]!;
    groups.push({
      document_id,
      display_name,
      site_name: head.site_name,
      site_id: head.site_id,
      anomalies,
      latest_at: head.updated_at,
    });
  }
  groups.sort((a, b) => new Date(b.latest_at).getTime() - new Date(a.latest_at).getTime());
  return groups;
}

/** §5 workflow label for anomaly inbox. */
function reviewStatusLabel(status: string): string {
  switch (status) {
    case "open":
      return "Open";
    case "approved":
      return "Approved";
    case "dismissed":
      return "Dismissed";
    case "flagged":
      return "Flagged";
    default:
      return status;
  }
}

/** §5e: confirm transition with optional audit note before POST …/review. */
function ReviewTransitionModal({
  actionLabel,
  note,
  busy,
  openedAtMs,
  onNoteChange,
  onConfirm,
  onCancel,
}: {
  actionLabel: string;
  note: string;
  busy: boolean;
  openedAtMs: number;
  onNoteChange: (value: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div
      className="review-modal-overlay"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target !== e.currentTarget) {
          return;
        }
        if (Date.now() - openedAtMs < 400) {
          return;
        }
        onCancel();
      }}
    >
      <div
        className="review-modal card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="review-modal-title"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h3 id="review-modal-title">{actionLabel}</h3>
        <p className="hint">Optional note is stored on the audit trail for this transition (§5e).</p>
        <label className="field">
          <span>Note</span>
          <textarea
            value={note}
            onChange={(e) => onNoteChange(e.target.value)}
            placeholder="e.g. Verified with store manager; expected seasonal spike."
            rows={4}
            maxLength={8000}
            disabled={busy}
          />
        </label>
        <div className="review-modal-actions">
          <button type="button" className="primary" disabled={busy} onClick={() => onConfirm()}>
            {busy ? "Saving…" : "Confirm"}
          </button>
          <button type="button" className="secondary" disabled={busy} onClick={() => onCancel()}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

/** §5b inline audit list under an anomaly row when expanded. */
function AnomalyReviewEventsPanel({ events, loading }: { events: AnomalyReviewEventResponse[]; loading: boolean }) {
  if (loading) {
    return <p className="hint review-events-loading">Loading review history…</p>;
  }
  if (events.length === 0) {
    return <p className="hint">No review transitions yet.</p>;
  }
  return (
    <ul className="review-events-list">
      {events.map((ev) => (
        <li key={ev.id} className="review-events-item">
          <span className="review-events-meta">
            {new Date(ev.created_at).toLocaleString()} — {reviewStatusLabel(ev.from_status)} →{" "}
            {reviewStatusLabel(ev.to_status)}
          </span>
          {ev.note ? <p className="review-events-note">{ev.note}</p> : null}
        </li>
      ))}
    </ul>
  );
}

/** §5a row actions — open §5e modal before POST; History toggles audit rows. */
function AnomalyReviewActions({
  row,
  busy,
  historyExpanded,
  historyLoading,
  onRequestReview,
  onToggleHistory,
}: {
  row: AnomalyResponse;
  busy: boolean;
  historyExpanded: boolean;
  historyLoading: boolean;
  onRequestReview: (e: MouseEvent<HTMLButtonElement>, anomalyId: string, to: AnomalyReviewStatus, label: string) => void;
  onToggleHistory: (e: MouseEvent<HTMLButtonElement>, anomalyId: string) => void;
}) {
  const s = row.review_status;
  const mk = (label: string, to: AnomalyReviewStatus, classExtra?: string) => (
    <button
      type="button"
      key={`${row.id}-${to}`}
      className={`secondary anomaly-action-btn${classExtra ? ` ${classExtra}` : ""}`}
      disabled={busy}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => onRequestReview(e, row.id, to, label)}
    >
      {label}
    </button>
  );
  let actions: ReactNode;
  if (s === "open") {
    actions = (
      <>
        {mk("Approve", "approved")}
        {mk("Dismiss", "dismissed")}
        {mk("Flag", "flagged", "anomaly-action-btn--flag")}
      </>
    );
  } else if (s === "flagged") {
    actions = (
      <>
        {mk("Approve", "approved")}
        {mk("Dismiss", "dismissed")}
        {mk("Reopen", "open")}
      </>
    );
  } else if (s === "approved" || s === "dismissed") {
    actions = (
      <>
        {mk("Reopen", "open")}
        {mk("Flag", "flagged", "anomaly-action-btn--flag")}
      </>
    );
  } else {
    actions = null;
  }
  return (
    <div className="anomaly-actions">
      {actions}
      <button
        type="button"
        className="secondary anomaly-action-btn anomaly-action-btn--history"
        disabled={busy || historyLoading}
        onClick={(e) => onToggleHistory(e, row.id)}
      >
        {historyLoading ? "…" : historyExpanded ? "Hide notes" : "History"}
      </button>
    </div>
  );
}

function storeSiteIdForOrg(orgId: string, siteId: string): void {
  try {
    const raw = localStorage.getItem(SITE_BY_ORG_STORAGE_KEY);
    const map = raw ? (JSON.parse(raw) as Record<string, string>) : {};
    if (siteId) {
      map[orgId] = siteId;
    } else {
      delete map[orgId];
    }
    localStorage.setItem(SITE_BY_ORG_STORAGE_KEY, JSON.stringify(map));
  } catch {
    /* ignore quota / private mode */
  }
}

/** Worker statuses where the viewer should show the pipeline overlay and poll. */
const PIPELINE_BUSY_STATUSES = new Set(["queued", "pending", "received"]);

function PipelineBusyOverlay({ label }: { label: string }) {
  return (
    <div className="pipeline-overlay" aria-busy="true" aria-live="polite">
      <div className="pipeline-overlay-inner">
        <span className="pipeline-spinner" aria-hidden />
        <span className="pipeline-overlay-label">{label}</span>
      </div>
    </div>
  );
}

/** Dice-friendly random strings for the org form (slug must stay URL-safe: letters, digits, hyphens). */
function randomToken(len = 10): string {
  const hex = crypto.randomUUID().replace(/-/g, "");
  return hex.slice(0, len);
}

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
  if (status === "unsupported") {
    return `${base} ${base}--unsupported`;
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

function documentRowLabel(row: { display_name: string | null; document_id: string }): string {
  return anomalyDocumentLabel(row);
}

const ANOMALY_TABLE_COL_COUNT = 9;

/** Anomalies grouped under each bill/document so org-wide inbox maps clearly to uploads. */
function AnomaliesGroupedInbox({
  groups,
  signalCount,
  documentFilter,
  onOpenDocument,
  reviewEventsExpandedId,
  reviewEventsLoadingId,
  reviewEventsByAnomalyId,
  anomalyReviewBusyId,
  onRequestReview,
  onToggleHistory,
}: {
  groups: AnomalyDocumentGroup[];
  signalCount: number;
  documentFilter: string;
  onOpenDocument: (documentId: string) => void;
  reviewEventsExpandedId: string | null;
  reviewEventsLoadingId: string | null;
  reviewEventsByAnomalyId: Record<string, AnomalyReviewEventResponse[]>;
  anomalyReviewBusyId: string | null;
  onRequestReview: (
    e: MouseEvent<HTMLButtonElement>,
    anomalyId: string,
    to: AnomalyReviewStatus,
    label: string,
  ) => void;
  onToggleHistory: (e: MouseEvent<HTMLButtonElement>, anomalyId: string) => void;
}) {
  return (
    <div className="anomaly-by-document">
      <p className="anomaly-by-document-summary" role="status">
        <strong>{signalCount}</strong> signal{signalCount === 1 ? "" : "s"} across{" "}
        <strong>{groups.length}</strong> document{groups.length === 1 ? "" : "s"}
        {documentFilter ? " (filtered)" : ""}.
      </p>
      {groups.map((group) => {
        const reviewRollup = rollupAnomalyReviewStatus(
          group.anomalies.map((a) => a.review_status),
        );
        const severityCounts = { critical: 0, warning: 0, info: 0 };
        for (const a of group.anomalies) {
          if (a.severity === "critical" || a.severity === "warning" || a.severity === "info") {
            severityCounts[a.severity] += 1;
          }
        }
        return (
          <section key={group.document_id} className="anomaly-doc-group card card--nested">
            <header className="anomaly-doc-group__header">
              <div className="anomaly-doc-group__title-block">
                <h3 className="anomaly-doc-group__title">{anomalyDocumentLabel(group)}</h3>
                <p className="anomaly-doc-group__meta">
                  <span>
                    {group.anomalies.length} signal{group.anomalies.length === 1 ? "" : "s"}
                  </span>
                  {group.site_name ? (
                    <>
                      <span className="anomaly-doc-group__sep">·</span>
                      <span>{group.site_name}</span>
                    </>
                  ) : null}
                  <span className="anomaly-doc-group__sep">·</span>
                  <code className="anomaly-doc-group__id" title={group.document_id}>
                    {group.document_id}
                  </code>
                </p>
              </div>
              <div className="anomaly-doc-group__badges">
                {severityCounts.critical > 0 ? (
                  <span className="comparison-severity comparison-severity--critical">
                    {severityCounts.critical} critical
                  </span>
                ) : null}
                {severityCounts.warning > 0 ? (
                  <span className="comparison-severity comparison-severity--warning">
                    {severityCounts.warning} warning
                  </span>
                ) : null}
                {severityCounts.info > 0 ? (
                  <span className="comparison-severity comparison-severity--info">
                    {severityCounts.info} info
                  </span>
                ) : null}
                {reviewRollup ? (
                  <span className={`review-status-pill review-status-pill--${reviewRollup}`}>
                    {reviewStatusLabel(reviewRollup)}
                  </span>
                ) : null}
              </div>
              <button
                type="button"
                className="secondary anomaly-doc-group__open"
                onClick={() => onOpenDocument(group.document_id)}
              >
                View bill
              </button>
            </header>
            <div className="table-wrap anomaly-doc-group__table">
              <table className="doc-table">
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Severity</th>
                    <th>Grounding</th>
                    <th>Rule</th>
                    <th>Explanation</th>
                    <th>Summary</th>
                    <th>Review</th>
                    <th>Note</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {group.anomalies.map((row) => (
                    <Fragment key={row.id}>
                      <tr
                        className="doc-table__row"
                        title={
                          row.explainability.reasons.length
                            ? row.explainability.reasons.join(" ")
                            : undefined
                        }
                        aria-label={`${row.title} — open ${anomalyDocumentLabel(group)}`}
                        {...getSelectableTableRowProps(() => onOpenDocument(row.document_id), {
                          extraInteractiveSelector: ".anomaly-actions-cell",
                        })}
                      >
                        <td>{new Date(row.updated_at).toLocaleString()}</td>
                        <td>
                          <span className={`comparison-severity comparison-severity--${row.severity}`}>
                            {comparisonSeverityLabel(row.severity)}
                          </span>
                        </td>
                        <td>
                          <span
                            className={`confidence-pill confidence-pill--${row.explainability.confidence}`}
                            title={row.explainability.version}
                          >
                            {explainConfidenceLabel(row.explainability.confidence)}
                          </span>
                        </td>
                        <td className="cell-mono">{row.rule_id}</td>
                        <td className="anomaly-explanation-cell">{row.explainability.explanation}</td>
                        <td>{row.summary}</td>
                        <td>
                          <span className={`review-status-pill review-status-pill--${row.review_status}`}>
                            {reviewStatusLabel(row.review_status)}
                          </span>
                        </td>
                        <td className="anomaly-note-cell" title={row.latest_review_note ?? undefined}>
                          {row.latest_review_note ?? "—"}
                        </td>
                        <td
                          className="anomaly-actions-cell"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <AnomalyReviewActions
                            row={row}
                            busy={anomalyReviewBusyId === row.id}
                            historyExpanded={reviewEventsExpandedId === row.id}
                            historyLoading={reviewEventsLoadingId === row.id}
                            onRequestReview={onRequestReview}
                            onToggleHistory={onToggleHistory}
                          />
                        </td>
                      </tr>
                      {reviewEventsExpandedId === row.id ? (
                        <tr className="review-events-row">
                          <td colSpan={ANOMALY_TABLE_COL_COUNT}>
                            <AnomalyReviewEventsPanel
                              events={reviewEventsByAnomalyId[row.id] ?? []}
                              loading={reviewEventsLoadingId === row.id}
                            />
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </div>
  );
}

function DocumentViewerPanel({
  headerDocumentId,
  viewer,
  loading,
  error,
  bill,
  billLoading,
  billError,
  onClose,
  onReprocess,
  onDelete,
  reprocessBusy,
  reprocessError,
  deleteBusy,
  deleteError,
  pipelineBusy,
  pipelineBusyLabel,
  sites,
  displayNameValue,
  onDisplayNameValueChange,
  onApplyDisplayName,
  onClearDisplayName,
  displayNameBusy,
  displayNameError,
  assignSiteValue,
  onAssignSiteValueChange,
  onApplySite,
  assignSiteBusy,
  assignSiteError,
  priorBills,
  priorBillsLoading,
  priorBillsError,
  onOpenPriorBill,
  comparison,
  comparisonLoading,
  comparisonError,
  onViewSignals,
}: {
  headerDocumentId: string | null;
  viewer: DocumentViewerResponse | null;
  loading: boolean;
  error: string | null;
  bill: BillResponse | null;
  billLoading: boolean;
  billError: string | null;
  onClose: () => void;
  /** When set, show **Reprocess** to re-enqueue the worker (stuck ``queued``, ``extracted`` without bill, etc.). */
  onReprocess?: () => void;
  onDelete?: () => void;
  reprocessBusy?: boolean;
  reprocessError?: string | null;
  deleteBusy?: boolean;
  deleteError?: string | null;
  /** Show spinner overlay (reprocess / worker / background refresh) without clearing prior content. */
  pipelineBusy?: boolean;
  pipelineBusyLabel?: string;
  sites?: SiteResponse[];
  displayNameValue?: string;
  onDisplayNameValueChange?: (value: string) => void;
  onApplyDisplayName?: () => void;
  onClearDisplayName?: () => void;
  displayNameBusy?: boolean;
  displayNameError?: string | null;
  assignSiteValue?: string;
  onAssignSiteValueChange?: (siteId: string) => void;
  onApplySite?: () => void;
  assignSiteBusy?: boolean;
  assignSiteError?: string | null;
  priorBills?: BillResponse[] | null;
  priorBillsLoading?: boolean;
  priorBillsError?: string | null;
  /** Open the document for a prior bill row (same site history). */
  onOpenPriorBill?: (documentId: string) => void;
  comparison?: DocumentComparisonResponse | null;
  comparisonLoading?: boolean;
  comparisonError?: string | null;
  /** Jump to Anomalies tab filtered to this document. */
  onViewSignals?: () => void;
}) {
  const showPanel =
    loading ||
    error ||
    !!viewer ||
    billLoading ||
    billError ||
    bill !== null ||
    reprocessBusy ||
    deleteBusy ||
    !!reprocessError ||
    !!deleteError;
  const reprocessBlocked = !viewer || viewer.processing_status === "awaiting_object";
  const unsupportedReprocessOk =
    viewer?.processing_status === "unsupported" &&
    viewer.unsupported_reason_code != null &&
    UNSUPPORTED_REPROCESS_MAY_HELP_CODES.has(viewer.unsupported_reason_code);
  const showReprocessButton =
    onReprocess &&
    !reprocessBlocked &&
    (viewer?.processing_status !== "unsupported" || unsupportedReprocessOk);
  const reprocessTitle = reprocessBlocked
    ? !viewer
      ? "Open a finalized document first."
      : "Finalize the upload before reprocessing."
    : unsupportedReprocessOk
      ? "Re-run extraction on this same file (e.g. after EXTRACTION_LLM_API_KEY was added)."
      : "Re-enqueue extraction + bill sync (safe after RQ crashes; may append another raw extraction).";
  if (!showPanel) {
    return null;
  }
  const statusPolling = viewer != null && PIPELINE_BUSY_STATUSES.has(viewer.processing_status);
  return (
    <section className="card doc-viewer-card doc-viewer-card--pipeline" aria-live="polite">
      {pipelineBusy ? (
        <PipelineBusyOverlay label={pipelineBusyLabel ?? "Processing document…"} />
      ) : null}
      <div className={`doc-viewer-body${pipelineBusy ? " doc-viewer-body--dimmed" : ""}`}>
      <div className="doc-viewer-toolbar">
        <h2 className="doc-viewer-title-wrap">
          {viewer?.display_name?.trim() ? (
            <span className="doc-viewer-display-name">{viewer.display_name.trim()}</span>
          ) : (
            "Document"
          )}
          {headerDocumentId ? (
            <code className="header-doc-id" title="Document UUID">
              {headerDocumentId}
            </code>
          ) : null}
        </h2>
        <div className="doc-viewer-toolbar-actions">
          {showReprocessButton ? (
            <button
              type="button"
              className="secondary"
              disabled={reprocessBusy || deleteBusy}
              title={reprocessTitle}
              onClick={() => onReprocess()}
            >
              {reprocessBusy ? "Reprocessing…" : "Reprocess"}
            </button>
          ) : null}
          <button type="button" className="secondary" onClick={onClose}>
            Close
          </button>
          {onDelete ? (
            <button
              type="button"
              className="btn-danger"
              disabled={deleteBusy || reprocessBusy || !viewer}
              title="Remove this document from your list (soft delete; file kept in storage for now)"
              onClick={() => onDelete()}
            >
              {deleteBusy ? "Deleting…" : "Delete"}
            </button>
          ) : null}
        </div>
      </div>
      {reprocessError ? <p className="error">{reprocessError}</p> : null}
      {deleteError ? <p className="error">{deleteError}</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {loading && !viewer ? (
        <div className="doc-preview-shell doc-preview-shell--loading">
          <span className="pipeline-spinner pipeline-spinner--inline" aria-hidden />
          <span className="hint">Loading preview…</span>
        </div>
      ) : null}
      {viewer ? (
        <>
          <div className="doc-preview-shell">
            <DocumentPreview viewer={viewer} />
          </div>
          <dl className="kv doc-viewer-kv">
            <dt>Name</dt>
            <dd>
              {onApplyDisplayName ? (
                <div className="site-assign-inline doc-name-assign">
                  <input
                    type="text"
                    className="doc-name-input"
                    value={displayNameValue ?? ""}
                    disabled={displayNameBusy}
                    placeholder="Optional label"
                    maxLength={255}
                    onChange={(e) => onDisplayNameValueChange?.(e.target.value)}
                    aria-label="Document display name"
                  />
                  <button
                    type="button"
                    className="secondary site-assign-btn"
                    disabled={displayNameBusy}
                    onClick={() => onApplyDisplayName()}
                  >
                    {displayNameBusy ? "Saving…" : "Save name"}
                  </button>
                  {onClearDisplayName ? (
                    <button
                      type="button"
                      className="secondary site-assign-btn"
                      disabled={displayNameBusy || !(viewer.display_name?.trim() || displayNameValue?.trim())}
                      onClick={() => onClearDisplayName()}
                    >
                      Clear
                    </button>
                  ) : null}
                </div>
              ) : viewer.display_name?.trim() ? (
                viewer.display_name.trim()
              ) : (
                "—"
              )}
              {displayNameError ? <p className="error site-assign-error">{displayNameError}</p> : null}
            </dd>
            <dt>Document ID</dt>
            <dd>
              <code>{viewer.document_id}</code>
            </dd>
            <dt>Organization</dt>
            <dd>
              <code>{viewer.organization_id}</code>
            </dd>
            <dt>Site</dt>
            <dd>
              {onApplySite && sites && sites.length > 0 ? (
                <div className="site-assign-inline">
                  <select
                    className="site-select"
                    value={assignSiteValue ?? ""}
                    disabled={assignSiteBusy}
                    onChange={(e) => onAssignSiteValueChange?.(e.target.value)}
                    aria-label="Site for this document"
                  >
                    <option value="">— No site —</option>
                    {sites.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="secondary site-assign-btn"
                    disabled={assignSiteBusy}
                    onClick={() => onApplySite()}
                  >
                    {assignSiteBusy ? "Saving…" : "Save site"}
                  </button>
                </div>
              ) : viewer.site_id ? (
                <code>{viewer.site_id}</code>
              ) : (
                "—"
              )}
              {assignSiteError ? <p className="error site-assign-error">{assignSiteError}</p> : null}
              {!viewer.site_id && sites && sites.length === 0 ? (
                <p className="hint">Create a site under Connection, then assign it here for bill history.</p>
              ) : null}
            </dd>
            <dt>Source</dt>
            <dd>{viewer.source}</dd>
            <dt>Status</dt>
            <dd>
              <span className={statusPillClass(viewer.processing_status)}>{viewer.processing_status}</span>
              {statusPolling ? (
                <span className="hint doc-status-poll-hint"> · auto-refresh until worker finishes</span>
              ) : null}
            </dd>
            {viewer.processing_error ? (
              <>
                <dt>Error</dt>
                <dd className="cell-error-inline">{viewer.processing_error}</dd>
              </>
            ) : null}
            {viewer.processing_status === "unsupported" && viewer.unsupported_reason ? (
              <>
                <dt>Notice</dt>
                <dd className="unsupported-notice">{viewer.unsupported_reason}</dd>
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
      {viewer?.processing_status === "unsupported" ? (
        <div className="bill-section">
          <h3 className="bill-section-title">Not a utility bill</h3>
          <p className="hint">
            This file was processed but is not saved as a bill, so comparison and signals are not run.{" "}
            {unsupportedReprocessOk ? (
              <>
                You can <strong>Reprocess</strong> the same file only if extraction settings changed (for example
                EXTRACTION_LLM_API_KEY was added). Otherwise{" "}
              </>
            ) : (
              <>
                <strong>Reprocess will not change the file</strong> — it only re-reads the same upload.{" "}
              </>
            )}
            <strong>Delete</strong> this document, then upload a utility invoice PDF from the Upload tab.
          </p>
        </div>
      ) : billLoading || billError || bill !== null ? (
        <div className="bill-section">
          <h3 className="bill-section-title">Normalized bill</h3>
          {billError ? <p className="error">{billError}</p> : null}
          {!billLoading && !billError && bill === null ? (
            <p className="hint">
              No bill row yet. If status is <strong>extracted</strong> but the bill never appeared, use{" "}
              <strong>Reprocess</strong>. While the document is queued for the worker, status and bill refresh here
              automatically.
            </p>
          ) : null}
          {bill ? (
            <>
              <dl className="kv bill-header-kv">
                <dt>Bill ID</dt>
                <dd>
                  <code>{bill.id}</code>
                </dd>
                <dt>Spend domain</dt>
                <dd>{bill.spend_domain}</dd>
                <dt>Spend kind</dt>
                <dd>{bill.spend_kind ?? "—"}</dd>
                <dt>Issuer</dt>
                <dd>{bill.issuer_name ?? "—"}</dd>
                <dt>Period</dt>
                <dd className="cell-mono">{formatBillPeriod(bill)}</dd>
                <dt>Total</dt>
                <dd>
                  {bill.total_amount != null && bill.total_amount !== undefined
                    ? formatMoney(bill.total_amount, bill.currency)
                    : "—"}
                </dd>
                <dt>Normalization</dt>
                <dd className="cell-mono">{bill.normalization_version}</dd>
                {bill.summary?.structured_via ? (
                  <>
                    <dt>Structured via</dt>
                    <dd className="cell-mono">{String(bill.summary.structured_via)}</dd>
                  </>
                ) : null}
                {bill.summary?.text_char_count != null && bill.summary?.text_char_count !== undefined ? (
                  <>
                    <dt>PDF text (embedded)</dt>
                    <dd>
                      {String(bill.summary.text_char_count)} chars
                      {bill.summary.text_extraction_method ? (
                        <span className="hint"> · {String(bill.summary.text_extraction_method)}</span>
                      ) : null}
                    </dd>
                  </>
                ) : null}
              </dl>
              {bill.summary?.structured_error ? (
                <p className="error bill-structured-error" role="alert">
                  {String(bill.summary.structured_error)}
                </p>
              ) : null}
              {bill.summary?.structured_via === "deterministic_fallback" &&
              !bill.summary?.structured_error ? (
                <p className="error bill-structured-error" role="alert">
                  LLM structuring failed (no error detail returned). Line items may be the dev sample — check
                  worker logs and EXTRACTION_LLM_* settings, then reprocess.
                </p>
              ) : null}
              {bill.summary?.structured_note ? (
                <p className="hint bill-structured-note">{String(bill.summary.structured_note)}</p>
              ) : null}
              {bill.summary?.text_needs_ocr === true ? (
                <p className="error">This file likely needs OCR (no embedded text layer).</p>
              ) : null}
              {bill.line_items.length > 0 ? (
                <div className="table-wrap bill-table-wrap">
                  <table className="bill-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Label</th>
                        <th>Kind</th>
                        <th>Service</th>
                        <th>Qty</th>
                        <th>Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bill.line_items.map((li) => (
                        <tr key={li.id}>
                          <td>{li.position}</td>
                          <td>{li.raw_label}</td>
                          <td className="cell-mono">{li.canonical_line_kind}</td>
                          <td className="cell-mono">{li.canonical_service_key ?? "—"}</td>
                          <td className="cell-mono">
                            {li.quantity != null ? `${li.quantity} ${li.quantity_unit ?? ""}`.trim() : "—"}
                          </td>
                          <td>{li.amount != null ? formatMoney(li.amount, li.currency) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="hint">Bill header exists but no line items.</p>
              )}
            </>
          ) : null}
          {comparisonLoading || comparisonError || comparison !== undefined ? (
            <div className="comparison-section" aria-live="polite">
              <div className="comparison-section__head">
                <h4 className="comparison-title">Comparison insights</h4>
                {onViewSignals ? (
                  <button type="button" className="secondary comparison-inbox-link" onClick={() => onViewSignals()}>
                    View in signals inbox
                  </button>
                ) : null}
              </div>
              <p className="comparison-note">
                We compare this bill to the <strong>previous</strong> one at the same site when history exists.
                We always check whether the header total matches line items on <strong>this</strong> bill (no AI).
                {comparison?.rule_pack_version ? (
                  <>
                    {" "}
                    <span className="cell-mono">({comparison.rule_pack_version})</span>
                  </>
                ) : null}
              </p>
              {comparisonError ? <p className="error">{comparisonError}</p> : null}
              {comparisonLoading ? (
                <p className="comparison-loading">
                  <span className="pipeline-spinner pipeline-spinner--inline" aria-hidden />
                  Checking against your last bill…
                </p>
              ) : null}
              {!comparisonLoading && comparison && comparison.findings.length === 0 && bill ? (
                <p className="comparison-empty">
                  All clear: nothing unusual found for this bill (including header vs line totals).
                </p>
              ) : null}
              {!comparisonLoading && comparison && comparisonIsInfoOnly(comparison) ? (
                <p className="comparison-baseline-callout" role="status">
                  {comparisonHasNoPriorBill(comparison)
                    ? "First bill at this site — saved as your baseline. Upload more months at the same location; when a second bill is on file, we compare each one to the prior period for month-over-month and new-fee checks. We still ran single-bill integrity checks (header vs lines, duplicate lines, fee share, penalty-style fees, and more)."
                    : "Setup note: assign a site or add history to enable full comparisons. Single-bill integrity checks still run when line data is available."}
                </p>
              ) : null}
              {!comparisonLoading && comparison && comparison.findings.length > 0 ? (
                <ul className="comparison-findings">
                  {comparison.findings.map((f) => (
                    <li
                      key={`${f.rule_id}-${f.title}`}
                      className={`comparison-finding comparison-finding--${f.severity}`}
                    >
                      <span className={`comparison-severity comparison-severity--${f.severity}`}>
                        {comparisonSeverityLabel(f.severity)}
                      </span>
                      <strong>{f.title}</strong>
                      <p>{f.summary}</p>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
          {priorBillsLoading || priorBillsError || priorBills !== undefined ? (
            <div className="prior-bills-section">
              <h4 className="prior-bills-title">Prior bills (same site)</h4>
              {priorBillsError ? <p className="error">{priorBillsError}</p> : null}
              {priorBillsLoading ? <p className="hint">Loading prior bills…</p> : null}
              {!priorBillsLoading && priorBills && priorBills.length === 0 ? (
                <p className="hint">
                  No prior bills for this site yet. Upload another month at the same site (in the sidebar) to enable comparisons.
                </p>
              ) : null}
              <p className="hint prior-bills-note">
                Sorted by billing period (newest first). Click a row to open that bill; drag across text to highlight
                and copy without opening.
              </p>
              {priorBills && priorBills.length > 0 ? (
                <div className="table-wrap bill-table-wrap">
                  <table className="bill-table">
                    <thead>
                      <tr>
                        <th>Period</th>
                        <th>Issuer</th>
                        <th>Total</th>
                        <th title="When this file was processed in the platform">Uploaded</th>
                      </tr>
                    </thead>
                    <tbody>
                      {priorBillsSortedByPeriod(priorBills).map((pb) => {
                        const openPrior = onOpenPriorBill
                          ? () => onOpenPriorBill(pb.document_id)
                          : undefined;
                        const isActive = headerDocumentId === pb.document_id;
                        return (
                          <tr
                            key={pb.id}
                            className={`bill-table__row${isActive ? " bill-table__row--selected" : ""}${openPrior ? "" : " bill-table__row--static"}`}
                            aria-label={
                              openPrior
                                ? `Open document for ${formatBillPeriod(pb)} bill`
                                : undefined
                            }
                            {...(openPrior
                              ? getSelectableTableRowProps(openPrior)
                              : {})}
                          >
                            <td className="cell-mono">{formatBillPeriod(pb)}</td>
                            <td>{pb.issuer_name ?? "—"}</td>
                            <td>{pb.total_amount != null ? formatMoney(pb.total_amount, pb.currency) : "—"}</td>
                            <td>{new Date(pb.created_at).toLocaleDateString()}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
      </div>
    </section>
  );
}

export function App() {
  const envApi = import.meta.env.VITE_API_BASE_URL;
  const envOrg = import.meta.env.VITE_ORG_ID;

  const [view, setView] = useState<AppView>("upload");
  const [apiBase, setApiBase] = useState(() => (envApi && envApi.length > 0 ? envApi : defaultApiBase));
  const [orgId, setOrgId] = useState(() => envOrg ?? "");
  const [authUser, setAuthUser] = useState<AuthUser | null>(() => getStoredUser());
  /** Default site for new uploads (per org, stored in localStorage). */
  const [selectedSiteId, setSelectedSiteId] = useState("");
  const [siteRows, setSiteRows] = useState<SiteResponse[]>([]);
  const [siteListLoading, setSiteListLoading] = useState(false);
  const [siteListError, setSiteListError] = useState<string | null>(null);
  const [newSiteName, setNewSiteName] = useState("Seattle");
  const [siteCreateBusy, setSiteCreateBusy] = useState(false);
  const [siteCreateMessage, setSiteCreateMessage] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  /** Optional label sent with presigned-upload (blank = unset). */
  const [uploadDisplayName, setUploadDisplayName] = useState("");
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
  const [documentBill, setDocumentBill] = useState<BillResponse | null>(null);
  const [billLoading, setBillLoading] = useState(false);
  const [billError, setBillError] = useState<string | null>(null);
  /** Bump after reprocess (or similar) to refetch viewer + bill without changing selection. */
  const [viewerReloadNonce, setViewerReloadNonce] = useState(0);
  const [reprocessBusy, setReprocessBusy] = useState(false);
  const [reprocessError, setReprocessError] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [assignSiteDraft, setAssignSiteDraft] = useState("");
  const [assignSiteBusy, setAssignSiteBusy] = useState(false);
  const [assignSiteError, setAssignSiteError] = useState<string | null>(null);
  const [displayNameDraft, setDisplayNameDraft] = useState("");
  const [displayNameBusy, setDisplayNameBusy] = useState(false);
  const [displayNameError, setDisplayNameError] = useState<string | null>(null);
  const [priorBills, setPriorBills] = useState<BillResponse[] | undefined>(undefined);
  const [priorBillsLoading, setPriorBillsLoading] = useState(false);
  const [priorBillsError, setPriorBillsError] = useState<string | null>(null);
  const [comparison, setComparison] = useState<DocumentComparisonResponse | null | undefined>(undefined);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [anomalyRows, setAnomalyRows] = useState<AnomalyResponse[]>([]);
  const [anomalyListLoading, setAnomalyListLoading] = useState(false);
  const [anomalyListError, setAnomalyListError] = useState<string | null>(null);
  /** §5c inbox filter: empty string = all statuses. */
  const [anomalyReviewFilter, setAnomalyReviewFilter] = useState<string>("");
  /** Narrow anomalies inbox to one bill/document (empty = all). */
  const [anomalyDocumentFilter, setAnomalyDocumentFilter] = useState("");
  const [anomalyDocumentFilterLabel, setAnomalyDocumentFilterLabel] = useState("");
  const [anomalyReviewBusyId, setAnomalyReviewBusyId] = useState<string | null>(null);
  /** §5e modal: set when user picks Approve/Dismiss/Flag/Reopen before POST. */
  const [pendingReview, setPendingReview] = useState<{
    anomalyId: string;
    toStatus: AnomalyReviewStatus;
    actionLabel: string;
  } | null>(null);
  const [reviewNoteDraft, setReviewNoteDraft] = useState("");
  const [reviewEventsExpandedId, setReviewEventsExpandedId] = useState<string | null>(null);
  const [reviewEventsByAnomalyId, setReviewEventsByAnomalyId] = useState<
    Record<string, AnomalyReviewEventResponse[]>
  >({});
  const [reviewEventsLoadingId, setReviewEventsLoadingId] = useState<string | null>(null);
  /** Timestamp when §5e modal opened (backdrop ignores dismiss briefly after). */
  const reviewModalOpenedAtRef = useRef(0);
  /** Keep spinner visible from reprocess click until worker finishes and bill refetch settles. */
  const [pipelineHold, setPipelineHold] = useState(false);
  const loadedViewerDocIdRef = useRef<string | null>(null);
  const loadedBillDocIdRef = useRef<string | null>(null);

  const [orgFormName, setOrgFormName] = useState("");
  const [orgFormSlug, setOrgFormSlug] = useState("");
  /** Ephemeral dev-only field (not sent to API); filled when you click **Randomize**. */
  const [orgScratchLabel, setOrgScratchLabel] = useState("");
  const [orgRows, setOrgRows] = useState<OrganizationResponse[]>([]);
  const [orgListLoading, setOrgListLoading] = useState(false);
  const [orgListError, setOrgListError] = useState<string | null>(null);
  const [orgCreateBusy, setOrgCreateBusy] = useState(false);
  const [orgCreateMessage, setOrgCreateMessage] = useState<string | null>(null);

  const phaseAllowsSubmit = phase === "idle" || phase === "done" || phase === "error";

  const effectiveOrgId = useMemo(() => orgId.trim(), [orgId]);
  const platformAdmin = isPlatformAdmin(authUser);
  const activeOrgRole = useMemo(() => {
    if (!effectiveOrgId || !isUuid(effectiveOrgId)) return null;
    const row = orgRows.find((o) => o.id === effectiveOrgId);
    return row?.my_role ?? (platformAdmin ? "org_admin" : null);
  }, [effectiveOrgId, orgRows, platformAdmin]);
  /** Org admin (or platform admin): sites, delete docs, invites, materialize. */
  const canManageActiveOrg = Boolean(
    authUser &&
      effectiveOrgId &&
      isUuid(effectiveOrgId) &&
      (platformAdmin || isOrgAdminRole(activeOrgRole)),
  );
  /** Member or org admin may upload and review (not viewers). */
  const canWriteActiveOrg = Boolean(
    authUser &&
      effectiveOrgId &&
      isUuid(effectiveOrgId) &&
      (platformAdmin || canWriteOrgRole(activeOrgRole)),
  );

  const submitBlockedReason = useMemo(() => {
    if (!apiBase.trim()) {
      return "Set API base URL.";
    }
    if (!authUser) {
      return "Sign in first.";
    }
    if (!effectiveOrgId || !isUuid(effectiveOrgId)) {
      return "Choose an organization under Connection.";
    }
    if (!canWriteActiveOrg) {
      return "You have read-only access to this organization.";
    }
    if (!file) {
      return "Choose a file.";
    }
    if (!phaseAllowsSubmit) {
      return "Wait for the current step to finish.";
    }
    return null;
  }, [apiBase, orgId, file, phaseAllowsSubmit, canWriteActiveOrg]);

  const canSubmit = submitBlockedReason === null;

  const closeViewer = useCallback(() => {
    setSelectedDocId(null);
    replaceDocQuery(null);
    setDocumentBill(null);
    setBillError(null);
    setBillLoading(false);
    setReprocessError(null);
    setAssignSiteError(null);
    setPriorBills(undefined);
    setPriorBillsError(null);
    setComparison(undefined);
    setComparisonError(null);
    setPipelineHold(false);
    loadedViewerDocIdRef.current = null;
    loadedBillDocIdRef.current = null;
  }, []);

  const loadSitesList = useCallback(async () => {
    if (!apiBase.trim() || !effectiveOrgId || !isUuid(effectiveOrgId)) {
      setSiteRows([]);
      setSiteListError(null);
      return;
    }
    setSiteListError(null);
    setSiteListLoading(true);
    try {
      const rows = await fetchSitesList(apiBase.trim(), effectiveOrgId);
      setSiteRows(rows);
      const stored = loadStoredSiteId(effectiveOrgId);
      if (stored && rows.some((s) => s.id === stored)) {
        setSelectedSiteId(stored);
      } else if (selectedSiteId && rows.some((s) => s.id === selectedSiteId)) {
        /* keep current selection */
      } else if (rows.length === 1) {
        setSelectedSiteId(rows[0].id);
        storeSiteIdForOrg(effectiveOrgId, rows[0].id);
      }
    } catch (e) {
      setSiteListError(e instanceof Error ? e.message : String(e));
      setSiteRows([]);
    } finally {
      setSiteListLoading(false);
    }
  }, [apiBase, effectiveOrgId]);

  useEffect(() => {
    void loadSitesList();
  }, [loadSitesList]);

  const handleCreateSite = useCallback(async () => {
    if (!apiBase.trim() || !effectiveOrgId || !isUuid(effectiveOrgId)) {
      setSiteCreateMessage("Set a valid Organization ID first.");
      return;
    }
    const name = newSiteName.trim();
    if (!name) {
      setSiteCreateMessage("Enter a site name (e.g. Seattle).");
      return;
    }
    setSiteCreateBusy(true);
    setSiteCreateMessage(null);
    try {
      const created = await createSite(apiBase.trim(), effectiveOrgId, name);
      setSiteCreateMessage(`Site ready: ${created.name}`);
      setSelectedSiteId(created.id);
      storeSiteIdForOrg(effectiveOrgId, created.id);
      await loadSitesList();
    } catch (e) {
      setSiteCreateMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setSiteCreateBusy(false);
    }
  }, [apiBase, orgId, newSiteName, loadSitesList]);

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
    if (!selectedDocId || !effectiveOrgId || !apiBase.trim()) {
      setDocumentViewer(null);
      setViewerError(null);
      setViewerLoading(false);
      return;
    }
    let cancelled = false;
    setReprocessError(null);
    const initialLoad = loadedViewerDocIdRef.current !== selectedDocId;
    if (initialLoad) {
      setDocumentViewer(null);
      setViewerLoading(true);
    }
    setViewerError(null);
    void fetchDocumentViewer(apiBase.trim(), effectiveOrgId, selectedDocId)
      .then((v) => {
        if (!cancelled) {
          setDocumentViewer(v);
          loadedViewerDocIdRef.current = selectedDocId;
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
  }, [selectedDocId, orgId, apiBase, viewerReloadNonce]);

  /** Load normalized bill (2d) in parallel with the viewer when a document is selected. */
  useEffect(() => {
    if (!selectedDocId || !effectiveOrgId || !apiBase.trim()) {
      setDocumentBill(null);
      setBillError(null);
      setBillLoading(false);
      return;
    }
    let cancelled = false;
    const initialLoad = loadedBillDocIdRef.current !== selectedDocId;
    if (initialLoad) {
      setDocumentBill(null);
      setBillLoading(true);
    }
    setBillError(null);
    void fetchDocumentBill(apiBase.trim(), effectiveOrgId, selectedDocId)
      .then((res) => {
        if (!cancelled) {
          setDocumentBill(res.bill);
          loadedBillDocIdRef.current = selectedDocId;
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setBillError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setBillLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedDocId, orgId, apiBase, viewerReloadNonce]);

  useEffect(() => {
    setAssignSiteDraft(documentViewer?.site_id ?? "");
    setAssignSiteError(null);
  }, [documentViewer?.document_id, documentViewer?.site_id]);

  useEffect(() => {
    setDisplayNameDraft(documentViewer?.display_name ?? "");
    setDisplayNameError(null);
  }, [documentViewer?.document_id, documentViewer?.display_name]);

  /** Load prior bills when current bill has a site (§3a). */
  useEffect(() => {
    if (!selectedDocId || !effectiveOrgId || !apiBase.trim()) {
      setPriorBills(undefined);
      return;
    }
    const siteId = documentViewer?.site_id ?? documentBill?.site_id;
    if (!siteId || documentViewer?.processing_status !== "extracted") {
      setPriorBills(undefined);
      setPriorBillsLoading(false);
      return;
    }
    let cancelled = false;
    setPriorBillsLoading(true);
    setPriorBillsError(null);
    void fetchDocumentPriorBills(apiBase.trim(), effectiveOrgId, selectedDocId)
      .then((res: DocumentPriorBillsResponse) => {
        if (!cancelled) {
          setPriorBills(res.prior_bills);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setPriorBillsError(e instanceof Error ? e.message : String(e));
          setPriorBills(undefined);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setPriorBillsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    selectedDocId,
    orgId,
    apiBase,
    documentViewer?.site_id,
    documentViewer?.processing_status,
    documentBill?.site_id,
    viewerReloadNonce,
  ]);

  /** Run §3b comparison when bill + site are available (same gate as prior bills). */
  useEffect(() => {
    if (!selectedDocId || !effectiveOrgId || !apiBase.trim()) {
      setComparison(undefined);
      return;
    }
    const siteId = documentViewer?.site_id ?? documentBill?.site_id;
    if (!siteId || !documentBill || documentViewer?.processing_status !== "extracted") {
      setComparison(undefined);
      setComparisonLoading(false);
      return;
    }
    let cancelled = false;
    setComparisonLoading(true);
    setComparisonError(null);
    void fetchDocumentComparison(apiBase.trim(), effectiveOrgId, selectedDocId)
      .then((res) => {
        if (!cancelled) {
          setComparison(res);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setComparisonError(e instanceof Error ? e.message : String(e));
          setComparison(undefined);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setComparisonLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [
    selectedDocId,
    orgId,
    apiBase,
    documentViewer?.site_id,
    documentViewer?.processing_status,
    documentBill,
    viewerReloadNonce,
  ]);

  const handleApplySiteToDocument = useCallback(async () => {
    if (!selectedDocId || !effectiveOrgId || !apiBase.trim()) {
      return;
    }
    setAssignSiteBusy(true);
    setAssignSiteError(null);
    try {
      const siteId = assignSiteDraft.trim() || null;
      await patchDocumentSite(apiBase.trim(), effectiveOrgId, selectedDocId, siteId);
      setViewerReloadNonce((n) => n + 1);
      if (siteId) {
        setSelectedSiteId(siteId);
        storeSiteIdForOrg(effectiveOrgId, siteId);
      }
    } catch (e) {
      setAssignSiteError(e instanceof Error ? e.message : String(e));
    } finally {
      setAssignSiteBusy(false);
    }
  }, [selectedDocId, orgId, apiBase, assignSiteDraft]);

  const handleApplyDisplayName = useCallback(async () => {
    if (!selectedDocId || !effectiveOrgId || !apiBase.trim()) {
      return;
    }
    setDisplayNameBusy(true);
    setDisplayNameError(null);
    try {
      const trimmed = displayNameDraft.trim();
      const updated = await patchDocumentDisplayName(
        apiBase.trim(),
        effectiveOrgId,
        selectedDocId,
        trimmed || null,
      );
      setDisplayNameDraft(updated.display_name ?? "");
      setDocumentViewer((prev) =>
        prev && prev.document_id === selectedDocId
          ? { ...prev, display_name: updated.display_name }
          : prev,
      );
      setDocRows((rows) =>
        rows.map((r) =>
          r.document_id === selectedDocId ? { ...r, display_name: updated.display_name } : r,
        ),
      );
    } catch (e) {
      setDisplayNameError(e instanceof Error ? e.message : String(e));
    } finally {
      setDisplayNameBusy(false);
    }
  }, [selectedDocId, effectiveOrgId, apiBase, displayNameDraft]);

  const handleClearDisplayName = useCallback(async () => {
    if (!selectedDocId || !effectiveOrgId || !apiBase.trim()) {
      return;
    }
    setDisplayNameBusy(true);
    setDisplayNameError(null);
    try {
      const updated = await patchDocumentDisplayName(
        apiBase.trim(),
        effectiveOrgId,
        selectedDocId,
        null,
      );
      setDisplayNameDraft("");
      setDocumentViewer((prev) =>
        prev && prev.document_id === selectedDocId
          ? { ...prev, display_name: updated.display_name }
          : prev,
      );
      setDocRows((rows) =>
        rows.map((r) =>
          r.document_id === selectedDocId ? { ...r, display_name: updated.display_name } : r,
        ),
      );
    } catch (e) {
      setDisplayNameError(e instanceof Error ? e.message : String(e));
    } finally {
      setDisplayNameBusy(false);
    }
  }, [selectedDocId, effectiveOrgId, apiBase]);

  /** Clear pipeline overlay once extraction finished and fetches are idle. */
  useEffect(() => {
    if (!pipelineHold) {
      return;
    }
    const st = documentViewer?.processing_status;
    const terminal = st === "extracted" || st === "failed" || st === "unsupported";
    if (terminal && !viewerLoading && !billLoading) {
      setPipelineHold(false);
    }
  }, [pipelineHold, documentViewer?.processing_status, viewerLoading, billLoading]);

  const runUpload = useCallback(async () => {
    if (!file || !effectiveOrgId) {
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
      const presign = await presignUpload(apiBase.trim(), effectiveOrgId, file, {
        siteId: selectedSiteId.trim() || null,
        displayName: uploadDisplayName.trim() || null,
      });

      setPhase("uploading");
      setMessage("Uploading to object storage…");
      await putFileToPresignedUrl(file, presign.upload_url, presign.headers, (loaded, total) => {
        setUploadPct(total > 0 ? Math.round((100 * loaded) / total) : 0);
      });

      setPhase("completing");
      setMessage("Finalizing document (server-side hash)…");
      const done = await completeUpload(apiBase.trim(), effectiveOrgId, presign.document_id);
      setResult(done);
      setPhase("done");
      setMessage("Upload complete.");
    } catch (e) {
      setPhase("error");
      setMessage(e instanceof Error ? e.message : String(e));
    }
  }, [apiBase, orgId, file, closeViewer, selectedSiteId, uploadDisplayName]);

  const loadDocumentList = useCallback(async () => {
    // Org may still be loading from sidebar — avoid flashing a bogus error (poll / navigation race).
    if (!apiBase.trim() || !effectiveOrgId || !isUuid(effectiveOrgId)) {
      setDocRows([]);
      setDocListError(null);
      return;
    }
    setDocListError(null);
    setDocListLoading(true);
    try {
      const rows = await fetchDocumentsList(apiBase.trim(), effectiveOrgId, 200);
      setDocRows(rows);
    } catch (e) {
      setDocListError(e instanceof Error ? e.message : String(e));
      setDocRows([]);
    } finally {
      setDocListLoading(false);
    }
  }, [apiBase, effectiveOrgId]);

  const loadAnomalyList = useCallback(
    async (opts?: { materializeFirst?: boolean }) => {
      if (!apiBase.trim() || !effectiveOrgId || !isUuid(effectiveOrgId)) {
        setAnomalyRows([]);
        setAnomalyListError(null);
        return;
      }
      setAnomalyListError(null);
      setAnomalyListLoading(true);
      try {
        if (opts?.materializeFirst) {
          await postMaterializeAnomalyComparisons(apiBase.trim(), effectiveOrgId, {
            siteId: selectedSiteId || undefined,
            limit: 500,
          });
        }
        const rows = await fetchAnomaliesList(apiBase.trim(), effectiveOrgId, {
          siteId: selectedSiteId || undefined,
          reviewStatus: anomalyReviewFilter ? (anomalyReviewFilter as AnomalyReviewStatus) : undefined,
          limit: 500,
        });
        setAnomalyRows(rows);
      } catch (e) {
        setAnomalyListError(e instanceof Error ? e.message : String(e));
        setAnomalyRows([]);
      } finally {
        setAnomalyListLoading(false);
      }
    },
    [apiBase, orgId, selectedSiteId, anomalyReviewFilter],
  );

  const handleRequestAnomalyReview = useCallback(
    (e: MouseEvent<HTMLButtonElement>, anomalyId: string, toStatus: AnomalyReviewStatus, actionLabel: string) => {
      e.stopPropagation();
      e.preventDefault();
      reviewModalOpenedAtRef.current = Date.now();
      setPendingReview({ anomalyId, toStatus, actionLabel });
      setReviewNoteDraft("");
    },
    [],
  );

  const handleCancelAnomalyReview = useCallback(() => {
    if (anomalyReviewBusyId) {
      return;
    }
    setPendingReview(null);
    setReviewNoteDraft("");
  }, [anomalyReviewBusyId]);

  const handleConfirmAnomalyReview = useCallback(async () => {
    if (!pendingReview || !apiBase.trim() || !effectiveOrgId || !isUuid(effectiveOrgId)) {
      return;
    }
    const { anomalyId, toStatus } = pendingReview;
    setAnomalyReviewBusyId(anomalyId);
    setAnomalyListError(null);
    try {
      const note = reviewNoteDraft.trim() || null;
      await postAnomalyReview(apiBase.trim(), effectiveOrgId, anomalyId, {
        to_status: toStatus,
        note,
      });
      setPendingReview(null);
      setReviewNoteDraft("");
      setReviewEventsByAnomalyId((prev) => {
        const next = { ...prev };
        delete next[anomalyId];
        return next;
      });
      await loadAnomalyList();
      if (reviewEventsExpandedId === anomalyId) {
        setReviewEventsLoadingId(anomalyId);
        try {
          const events = await fetchAnomalyReviewEvents(apiBase.trim(), effectiveOrgId, anomalyId);
          setReviewEventsByAnomalyId((prev) => ({ ...prev, [anomalyId]: events }));
        } catch (err) {
          setAnomalyListError(err instanceof Error ? err.message : String(err));
        } finally {
          setReviewEventsLoadingId(null);
        }
      }
    } catch (err) {
      setAnomalyListError(err instanceof Error ? err.message : String(err));
    } finally {
      setAnomalyReviewBusyId(null);
    }
  }, [
    pendingReview,
    apiBase,
    orgId,
    reviewNoteDraft,
    loadAnomalyList,
    reviewEventsExpandedId,
  ]);

  const handleToggleAnomalyReviewHistory = useCallback(
    async (e: MouseEvent<HTMLButtonElement>, anomalyId: string) => {
      e.stopPropagation();
      e.preventDefault();
      if (reviewEventsExpandedId === anomalyId) {
        setReviewEventsExpandedId(null);
        return;
      }
      if (!apiBase.trim() || !effectiveOrgId || !isUuid(effectiveOrgId)) {
        return;
      }
      setReviewEventsExpandedId(anomalyId);
      if (reviewEventsByAnomalyId[anomalyId]) {
        return;
      }
      setReviewEventsLoadingId(anomalyId);
      setAnomalyListError(null);
      try {
        const events = await fetchAnomalyReviewEvents(apiBase.trim(), effectiveOrgId, anomalyId);
        setReviewEventsByAnomalyId((prev) => ({ ...prev, [anomalyId]: events }));
      } catch (err) {
        setAnomalyListError(err instanceof Error ? err.message : String(err));
      } finally {
        setReviewEventsLoadingId(null);
      }
    },
    [apiBase, orgId, reviewEventsExpandedId, reviewEventsByAnomalyId],
  );

  const goToDocuments = useCallback(() => {
    setView("documents");
    setSelectedDocId(docIdFromSearch());
    void loadDocumentList();
  }, [loadDocumentList]);

  const goToAnomalies = useCallback(() => {
    setView("anomalies");
    closeViewer();
  }, [closeViewer]);

  const goToAnomaliesForDocument = useCallback(
    (documentId: string, label: string) => {
      setAnomalyDocumentFilter(documentId);
      setAnomalyDocumentFilterLabel(label);
      setView("anomalies");
      closeViewer();
    },
    [closeViewer],
  );

  useEffect(() => {
    if (view !== "anomalies") {
      return;
    }
    void loadAnomalyList();
  }, [view, loadAnomalyList]);

  /** Load document list when org context becomes ready (avoids race on first navigation). */
  useEffect(() => {
    if (view !== "documents") {
      return;
    }
    if (!apiBase.trim() || !effectiveOrgId || !isUuid(effectiveOrgId)) {
      return;
    }
    void loadDocumentList();
  }, [view, apiBase, effectiveOrgId, loadDocumentList]);

  /** Poll viewer + bill while pipeline may still be running (no full-page reload). */
  useEffect(() => {
    if (!selectedDocId || !effectiveOrgId || !apiBase.trim()) {
      return;
    }
    const status = documentViewer?.processing_status;
    const busy = status === "queued" || status === "pending" || status === "received";
    if (!busy) {
      return;
    }
    const tick = () => {
      setViewerReloadNonce((n) => n + 1);
      if (view === "documents") {
        void loadDocumentList();
      }
    };
    const id = window.setInterval(tick, PIPELINE_POLL_MS);
    return () => window.clearInterval(id);
  }, [selectedDocId, orgId, apiBase, documentViewer?.processing_status, view, loadDocumentList]);

  const loadOrganizationsList = useCallback(async () => {
    if (!apiBase.trim()) {
      setOrgListError("Set API base URL first.");
      return;
    }
    setOrgListError(null);
    setOrgListLoading(true);
    try {
      const rows = await fetchOrganizationsList(apiBase.trim(), 200);
      setOrgRows(rows);
      if (rows.length === 1) {
        setOrgId(rows[0].id);
      } else if (orgId && !rows.some((r) => r.id === orgId) && rows.length > 0) {
        setOrgId(rows[0].id);
      }
    } catch (e) {
      setOrgListError(e instanceof Error ? e.message : String(e));
      setOrgRows([]);
    } finally {
      setOrgListLoading(false);
    }
  }, [apiBase, orgId]);

  useEffect(() => {
    if (authUser) {
      void loadOrganizationsList();
    }
  }, [authUser, loadOrganizationsList]);

  const randomizeOrgForm = useCallback(() => {
    const tok = randomToken(10);
    setOrgFormName(`Random tenant ${tok}`);
    setOrgFormSlug(`org-${tok}`);
    setOrgScratchLabel(`pilot-${randomToken(8)} (not saved)`);
  }, []);

  const submitCreateOrganization = useCallback(async () => {
    if (!apiBase.trim()) {
      setOrgCreateMessage("Set API base URL.");
      return;
    }
    const name = orgFormName.trim();
    const slug = orgFormSlug.trim();
    if (!name || !slug) {
      setOrgCreateMessage("Enter display name and slug (or click Randomize).");
      return;
    }
    setOrgCreateBusy(true);
    setOrgCreateMessage(null);
    try {
      const created = await createOrganization(apiBase.trim(), { name, slug });
      setOrgCreateMessage(`Created: ${created.name} — UUID copied to Connection below.`);
      setOrgId(created.id);
      await loadOrganizationsList();
    } catch (e) {
      setOrgCreateMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setOrgCreateBusy(false);
    }
  }, [apiBase, orgFormName, orgFormSlug, loadOrganizationsList]);

  const goToOrganizations = useCallback(() => {
    setView("organizations");
    closeViewer();
    void loadOrganizationsList();
  }, [closeViewer, loadOrganizationsList]);

  const goToUpload = useCallback(() => {
    setView("upload");
    closeViewer();
  }, [closeViewer]);

  const goToAccount = useCallback(() => {
    setView("account");
    closeViewer();
  }, [closeViewer]);

  const openDocumentInViewer = useCallback((documentId: string) => {
    setSelectedDocId(documentId);
    replaceDocQuery(documentId);
  }, []);

  const openAnomalyContext = useCallback(
    (documentId: string) => {
      setView("documents");
      openDocumentInViewer(documentId);
    },
    [openDocumentInViewer],
  );

  const filteredAnomalyRows = useMemo(() => {
    if (!anomalyDocumentFilter) {
      return anomalyRows;
    }
    return anomalyRows.filter((r) => r.document_id === anomalyDocumentFilter);
  }, [anomalyRows, anomalyDocumentFilter]);

  const anomalyGroupsFiltered = useMemo(
    () => groupAnomaliesByDocument(filteredAnomalyRows),
    [filteredAnomalyRows],
  );

  const handleAnomalyDocumentFilterChange = useCallback((documentId: string, label: string) => {
    setAnomalyDocumentFilter(documentId);
    setAnomalyDocumentFilterLabel(label);
  }, []);

  const handleReprocessSelected = useCallback(async () => {
    if (!selectedDocId || !effectiveOrgId || !apiBase.trim()) {
      return;
    }
    setReprocessBusy(true);
    setReprocessError(null);
    setPipelineHold(true);
    try {
      await reprocessDocument(apiBase.trim(), effectiveOrgId, selectedDocId);
      setViewerReloadNonce((n) => n + 1);
      if (view === "documents") {
        void loadDocumentList();
      }
    } catch (e) {
      setReprocessError(e instanceof Error ? e.message : String(e));
    } finally {
      setReprocessBusy(false);
    }
  }, [selectedDocId, orgId, apiBase, view, loadDocumentList]);

  const handleDeleteSelected = useCallback(async () => {
    if (!selectedDocId || !effectiveOrgId || !apiBase.trim()) {
      return;
    }
    const ok = window.confirm(
      "Delete this document from your list?\n\nThe file stays in storage for now (soft delete). You can upload it again later.",
    );
    if (!ok) {
      return;
    }
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await deleteDocument(apiBase.trim(), effectiveOrgId, selectedDocId);
      closeViewer();
      if (view === "documents") {
        void loadDocumentList();
      }
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeleteBusy(false);
    }
  }, [selectedDocId, orgId, apiBase, documentViewer?.document_id, closeViewer, view, loadDocumentList]);

  const pipelineStatusBusy =
    !!documentViewer &&
    PIPELINE_BUSY_STATUSES.has(documentViewer.processing_status);

  const pipelineBusy =
    reprocessBusy ||
    pipelineHold ||
    pipelineStatusBusy ||
    (viewerLoading && !documentViewer) ||
    (billLoading && !documentBill);

  const pipelineBusyLabel = reprocessBusy
    ? "Starting reprocess…"
    : pipelineStatusBusy
      ? "Document is being processed…"
      : "Updating bill…";

  const viewerSiteProps = {
    sites: siteRows,
    displayNameValue: displayNameDraft,
    onDisplayNameValueChange: setDisplayNameDraft,
    onApplyDisplayName: () => void handleApplyDisplayName(),
    onClearDisplayName: () => void handleClearDisplayName(),
    displayNameBusy,
    displayNameError,
    assignSiteValue: assignSiteDraft,
    onAssignSiteValueChange: setAssignSiteDraft,
    onApplySite: () => void handleApplySiteToDocument(),
    onDelete: () => void handleDeleteSelected(),
    assignSiteBusy,
    assignSiteError,
    deleteBusy,
    deleteError,
    priorBills,
    priorBillsLoading,
    priorBillsError,
    onOpenPriorBill: openDocumentInViewer,
    comparison,
    comparisonLoading,
    comparisonError,
    onViewSignals:
      documentViewer?.document_id != null
        ? () =>
            goToAnomaliesForDocument(
              documentViewer.document_id,
              documentViewer.display_name?.trim()
                ? documentViewer.display_name.trim()
                : anomalyDocumentLabel({
                    document_id: documentViewer.document_id,
                    display_name: documentViewer.display_name,
                  }),
            )
        : undefined,
  };

  const resetTokenFromUrl =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("reset_token")
      : null;

  useEffect(() => {
    if (!authUser || !apiBase.trim()) return;
    const params = new URLSearchParams(window.location.search);
    const inviteToken = params.get("invite_token");
    if (!inviteToken?.trim()) return;
    void (async () => {
      try {
        const res = await acceptOrganizationInvite(apiBase.trim(), inviteToken.trim());
        setOrgId(res.organization_id);
        if (params.has("invite_token")) {
          params.delete("invite_token");
          const q = params.toString();
          window.history.replaceState({}, "", `${window.location.pathname}${q ? `?${q}` : ""}`);
        }
        void loadOrganizationsList();
        alert(res.message);
      } catch (e) {
        alert(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [authUser, apiBase, loadOrganizationsList]);

  if (!authUser) {
    return (
      <LoginPage
        initialApiBase={apiBase}
        resetToken={resetTokenFromUrl}
        onSignedIn={(user, base) => {
          setAuthUser(user);
          setApiBase(base);
        }}
      />
    );
  }

  /** Derived labels for topbar and context badge. */
  const activeOrgName  = orgRows.find((o) => o.id === effectiveOrgId)?.name;
  const activeSiteName = siteRows.find((s) => s.id === selectedSiteId)?.name;

  const currentPageTitle =
    view === "upload"
      ? "Upload a bill"
      : view === "documents"
        ? "Documents"
        : view === "anomalies"
          ? "Anomaly inbox"
          : view === "account"
            ? "Account settings"
            : view === "pdf-generator"
              ? "PDF Generator"
              : "Organizations";

  const currentPageSubtitle =
    view === "upload"
      ? "Add a PDF utility bill — we extract line items, compare month-over-month, and highlight anything worth a second look."
      : view === "documents"
        ? "Track processing, open the PDF and extracted bill, assign a site, and see comparison insights alongside prior months."
        : view === "anomalies"
          ? "Saved comparison signals across your organization. Use filters to narrow by bill or review status."
          : view === "account"
            ? "Update your login email and password."
            : view === "pdf-generator"
              ? "Generate synthetic utility bills with embedded text for pipeline testing. Bills are created entirely in the browser — no API call needed."
              : "Create and manage organizations, sites, and team members.";

  return (
    <div className="app-shell">
      {/* ══════ Sidebar ══════ */}
      <aside className="app-sidebar">
        {/* Brand lockup */}
        <div className="sidebar-brand">
          <div className="sidebar-brand__icon" aria-hidden="true">SI</div>
          <div className="sidebar-brand__info">
            <span className="sidebar-brand__name">Spend Integrity</span>
            <span className="sidebar-brand__tagline">Utility bill intelligence</span>
          </div>
        </div>

        {/* Primary navigation */}
        <nav className="sidebar-nav" aria-label="Primary navigation">
          <button
            type="button"
            className={`sidebar-nav__item${view === "upload" ? " active" : ""}`}
            onClick={goToUpload}
            aria-current={view === "upload" ? "page" : undefined}
          >
            {/* Upload icon */}
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            <span>Upload</span>
          </button>
          <button
            type="button"
            className={`sidebar-nav__item${view === "documents" ? " active" : ""}`}
            onClick={() => void goToDocuments()}
            aria-current={view === "documents" ? "page" : undefined}
          >
            {/* Documents icon */}
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
            <span>Documents</span>
          </button>
          <button
            type="button"
            className={`sidebar-nav__item${view === "anomalies" ? " active" : ""}`}
            onClick={() => goToAnomalies()}
            aria-current={view === "anomalies" ? "page" : undefined}
          >
            {/* Anomalies / alert icon */}
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <span>Anomalies</span>
          </button>
          <button
            type="button"
            className={`sidebar-nav__item${view === "organizations" ? " active" : ""}`}
            onClick={() => void goToOrganizations()}
            aria-current={view === "organizations" ? "page" : undefined}
          >
            {/* Organizations / building icon */}
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16"/></svg>
            <span>Organizations</span>
          </button>
          <button
            type="button"
            className={`sidebar-nav__item${view === "account" ? " active" : ""}`}
            onClick={goToAccount}
            aria-current={view === "account" ? "page" : undefined}
          >
            {/* Account / user icon */}
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            <span>Account</span>
          </button>

          {/* Admin-only section */}
          {platformAdmin && (
            <>
              <div className="sidebar-nav__divider" role="separator" aria-label="Admin tools" />
              <button
                type="button"
                className={`sidebar-nav__item sidebar-nav__item--admin${view === "pdf-generator" ? " active" : ""}`}
                onClick={() => setView("pdf-generator")}
                aria-current={view === "pdf-generator" ? "page" : undefined}
              >
                {/* Sparkle / wand icon */}
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17 5.8 21.3l2.4-7.4L2 9.4h7.6z"/></svg>
                <span>PDF Generator</span>
                <span className="sidebar-nav__admin-badge">Admin</span>
              </button>
            </>
          )}
        </nav>

        {/* Org + site context selectors */}
        <div className="sidebar-context">
          <div className="sidebar-context__section">
            <span className="sidebar-context__label">Organization</span>
            <select
              className="sidebar-context__select"
              value={orgId}
              disabled={orgListLoading || orgRows.length === 0}
              onChange={(e) => setOrgId(e.target.value)}
              aria-label="Active organization"
            >
              <option value="">
                {orgRows.length === 0 ? "— No organizations —" : "— Select organization —"}
              </option>
              {orgRows.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
            {orgListError ? <p className="sidebar-context__error">{orgListError}</p> : null}
          </div>
          <div className="sidebar-context__section">
            <span className="sidebar-context__label">Site (location)</span>
            <select
              className="sidebar-context__select"
              value={selectedSiteId}
              disabled={!isUuid(effectiveOrgId) || siteListLoading || siteRows.length === 0}
              onChange={(e) => {
                const v = e.target.value;
                setSelectedSiteId(v);
                if (isUuid(effectiveOrgId)) {
                  storeSiteIdForOrg(effectiveOrgId, v);
                }
              }}
              aria-label="Active site"
            >
              <option value="">
                {siteRows.length === 0 ? "— No sites —" : "— Select site —"}
              </option>
              {siteRows.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            {siteListError ? <p className="sidebar-context__error">{siteListError}</p> : null}
          </div>
        </div>

        {/* User info + quick actions */}
        <div className="sidebar-user">
          <div className="sidebar-user__info">
            <div className="sidebar-user__avatar" aria-hidden="true">
              {authUser.email[0].toUpperCase()}
            </div>
            <div className="sidebar-user__details">
              <span className="sidebar-user__email" title={authUser.email}>
                {authUser.email}
              </span>
              <span className="sidebar-user__role">
                {platformAdmin
                  ? "Platform admin"
                  : activeOrgRole
                    ? activeOrgRole.replace("_", " ")
                    : "No org selected"}
              </span>
            </div>
          </div>
          <div className="sidebar-user__actions">
            <button
              type="button"
              className="sidebar-user__btn"
              title="Account settings"
              onClick={goToAccount}
            >
              {/* Settings icon */}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
            </button>
            <button
              type="button"
              className="sidebar-user__btn sidebar-user__btn--danger"
              title="Sign out"
              onClick={() => {
                clearSession();
                setAuthUser(null);
                setOrgId("");
                setOrgRows([]);
              }}
            >
              {/* Sign-out icon */}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
            </button>
          </div>
        </div>
      </aside>

      {/* ══════ Main content ══════ */}
      <main className="app-main">
        {/* Top bar: page title, subtitle, and context badge */}
        <div className="app-topbar">
          <div className="app-topbar__heading">
            <h1 className="app-topbar__title">{currentPageTitle}</h1>
            <p className="app-topbar__subtitle">{currentPageSubtitle}</p>
          </div>
          {(activeOrgName || activeSiteName) ? (
            <div className="app-topbar__context">
              <span className="context-badge">
                {activeOrgName ?? "No org"}
                {activeSiteName ? ` · ${activeSiteName}` : ""}
              </span>
            </div>
          ) : null}
        </div>

        {/* Per-view content */}
        <div className="app-content">
          {view === "upload" && (
        <>
          <section className="card">
            <h2>Send your file</h2>
            <p className="card-subtitle">PDFs go straight to secure storage, then the worker extracts and normalizes the bill.</p>
            {selectedSiteId && siteRows.some((s) => s.id === selectedSiteId) ? (
              <p className="hint">
                Uploads will use site: <strong>{siteRows.find((s) => s.id === selectedSiteId)?.name}</strong>
              </p>
            ) : (
              <p className="hint">Select a site in the sidebar so bills can be compared by location.</p>
            )}
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
            <label className="upload-name-field">
              <span className="upload-name-label">Document name (optional)</span>
              <input
                type="text"
                className="doc-name-input"
                value={uploadDisplayName}
                maxLength={255}
                placeholder="e.g. March 2026 — Main Street"
                onChange={(e) => setUploadDisplayName(e.target.value)}
              />
            </label>
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
                <div className="progress-track">
                  <div
                    className="progress-bar"
                    style={{
                      width: `${phase === "uploading" ? uploadPct : phase === "done" ? 100 : phase === "completing" ? 92 : 8}%`,
                    }}
                  />
                </div>
                <p className="status">{message}</p>
              </div>
            ) : null}
            {phase === "error" ? <p className="error">{message}</p> : null}
          </section>

          {result ? (
            <section className="card success">
              <h2>Done</h2>
              <p className="card-subtitle">Your upload is registered. Open it below or jump to the full list.</p>
              {selectedSiteId && siteRows.some((s) => s.id === selectedSiteId) ? (
                <p className="hint upload-baseline-note">
                  If this is the <strong>first bill</strong> at{" "}
                  <strong>{siteRows.find((s) => s.id === selectedSiteId)?.name}</strong>, we save it as your
                  baseline. Upload <strong>more months</strong> at the same site; each new bill is compared to the prior period for month-over-month checks. We
                  still run integrity checks on every bill (header vs lines, duplicate lines, fee share, and more).
                </p>
              ) : (
                <p className="hint upload-baseline-note">
                  Assign a <strong>site</strong> on the document (or pick one in the sidebar before the next upload)
                  so bills at the same location can be compared over time.
                </p>
              )}
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
                headerDocumentId={selectedDocId}
                viewer={documentViewer?.document_id === result.document_id ? documentViewer : null}
                loading={viewerLoading && selectedDocId === result.document_id}
                error={selectedDocId === result.document_id ? viewerError : null}
                bill={selectedDocId === result.document_id ? documentBill : null}
                billLoading={selectedDocId === result.document_id ? billLoading : false}
                billError={selectedDocId === result.document_id ? billError : null}
                onClose={closeViewer}
                onReprocess={() => void handleReprocessSelected()}
                reprocessBusy={reprocessBusy}
                reprocessError={reprocessError}
                pipelineBusy={
                  pipelineBusy &&
                  !!documentViewer &&
                  documentViewer.document_id === result.document_id &&
                  selectedDocId === result.document_id
                }
                pipelineBusyLabel={pipelineBusyLabel}
                {...viewerSiteProps}
              />
            </section>
          ) : null}
        </>
      )}
      {view === "documents" && (
        <div className="doc-layout">
          <section className="card doc-layout-list">
            <div className="doc-list-toolbar">
              <h2>All uploads</h2>
              <button type="button" disabled={docListLoading} onClick={() => void loadDocumentList()}>
                {docListLoading ? "Loading…" : "Refresh"}
              </button>
            </div>
            <p className="doc-list-lede">
              Newest first. Click a row to preview the file and review the extracted bill; drag across text to copy
              without opening. Use <strong>Signals</strong> for comparison signals in the Anomalies tab.
            </p>
            {docListError ? <p className="error">{docListError}</p> : null}
            {!docListError && !docListLoading && docRows.length === 0 ? (
              <p className="hint">No documents yet for this organization.</p>
            ) : null}
            {docRows.length > 0 ? (
              <div className="table-wrap">
                <table className="doc-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Created</th>
                      <th>Status</th>
                      <th>Review</th>
                      <th>Error</th>
                      <th>Source</th>
                      <th>MIME</th>
                      <th>Size</th>
                      <th>Signals</th>
                      <th>Document ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {docRows.map((row) => (
                      <tr
                        key={row.document_id}
                        className={`doc-table__row${selectedDocId === row.document_id ? " doc-table__row--selected" : ""}`}
                        aria-label={`Open document ${documentRowLabel(row)}`}
                        {...getSelectableTableRowProps(() => openDocumentInViewer(row.document_id), {
                          extraInteractiveSelector: ".doc-table__action-cell",
                        })}
                      >
                        <td className="doc-table__name">{row.display_name?.trim() || "—"}</td>
                        <td>{new Date(row.created_at).toLocaleString()}</td>
                        <td>
                          <span className={statusPillClass(row.processing_status)}>{row.processing_status}</span>
                        </td>
                        <td>
                          {row.anomaly_review_status ? (
                            <span
                              className={`review-status-pill review-status-pill--${row.anomaly_review_status}`}
                            >
                              {reviewStatusLabel(row.anomaly_review_status)}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td
                          className={row.processing_status === "unsupported" ? "cell-unsupported" : "cell-error"}
                          title={row.unsupported_reason ?? row.processing_error ?? undefined}
                        >
                          {row.processing_status === "unsupported" && row.unsupported_reason
                            ? row.unsupported_reason
                            : row.processing_error
                              ? row.processing_error
                              : "—"}
                        </td>
                        <td>{row.source}</td>
                        <td className="cell-mono">{row.mime_type}</td>
                        <td>{formatBytes(row.byte_size)}</td>
                        <td
                          className="doc-table__action-cell"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            type="button"
                            className="doc-table__link-btn"
                            title="Open saved comparison signals for this bill"
                            onClick={() =>
                              goToAnomaliesForDocument(row.document_id, documentRowLabel(row))
                            }
                          >
                            {row.anomaly_review_status ? "View signals" : "Signals"}
                          </button>
                        </td>
                        <td className="cell-mono cell-id">{row.document_id}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            <p className="hint doc-table-hint">Tip: unfinished uploads (no object in storage yet) return 400 from the viewer API until you complete the PUT flow.</p>
          </section>
          <DocumentViewerPanel
            headerDocumentId={selectedDocId}
            viewer={documentViewer}
            loading={viewerLoading}
            error={viewerError}
            bill={documentBill}
            billLoading={billLoading}
            billError={billError}
            onClose={closeViewer}
            onReprocess={() => void handleReprocessSelected()}
            reprocessBusy={reprocessBusy}
            reprocessError={reprocessError}
            pipelineBusy={pipelineBusy}
            pipelineBusyLabel={pipelineBusyLabel}
            {...viewerSiteProps}
          />
        </div>
      )}
      {view === "anomalies" && (
        <section className="card">
          <div className="doc-list-toolbar">
            <h2>Saved comparison signals</h2>
            <div className="anomaly-toolbar-controls">
              <AnomalyDocumentFilter
                apiBase={apiBase}
                orgId={effectiveOrgId}
                value={anomalyDocumentFilter}
                selectedLabel={anomalyDocumentFilterLabel}
                openDisabled={!effectiveOrgId || !isUuid(effectiveOrgId)}
                onChange={handleAnomalyDocumentFilterChange}
              />
              <label className="field field--inline anomaly-filter-field">
                <span>Review status</span>
                <select
                  value={anomalyReviewFilter}
                  onChange={(e) => setAnomalyReviewFilter(e.target.value)}
                  aria-label="Filter anomalies by review status"
                >
                  <option value="">All</option>
                  <option value="open">Open</option>
                  <option value="approved">Approved</option>
                  <option value="dismissed">Dismissed</option>
                  <option value="flagged">Flagged</option>
                </select>
              </label>
              <button
                type="button"
                disabled={anomalyListLoading}
                onClick={() => void loadAnomalyList({ materializeFirst: true })}
              >
                {anomalyListLoading ? "Loading…" : "Refresh"}
              </button>
            </div>
          </div>
          <p className="doc-list-lede">
            Signals are grouped by <strong>bill / document</strong>. Click a signal row to open that bill;
            drag across text to copy without opening. Use <strong>Filter by bill</strong> or{" "}
            <strong>View bill</strong> on a group header. <strong>Refresh</strong> runs comparison on finished
            bills (optionally filtered by site under Connection).
          </p>
          {anomalyListError ? <p className="error">{anomalyListError}</p> : null}
          {!anomalyListError && !anomalyListLoading && anomalyRows.length === 0 ? (
            <p className="hint">
              No anomalies yet. Bills must be normalized (<code>extracted</code>) with a site when you
              care about same-site history. Click <strong>Refresh</strong> to run comparison for all
              eligible documents and load this list, or open a document to run comparison for that bill only.
            </p>
          ) : null}
          {filteredAnomalyRows.length > 0 ? (
            <AnomaliesGroupedInbox
              groups={anomalyGroupsFiltered}
              signalCount={filteredAnomalyRows.length}
              documentFilter={anomalyDocumentFilter}
              onOpenDocument={openAnomalyContext}
              reviewEventsExpandedId={reviewEventsExpandedId}
              reviewEventsLoadingId={reviewEventsLoadingId}
              reviewEventsByAnomalyId={reviewEventsByAnomalyId}
              anomalyReviewBusyId={anomalyReviewBusyId}
              onRequestReview={handleRequestAnomalyReview}
              onToggleHistory={handleToggleAnomalyReviewHistory}
            />
          ) : null}
          {anomalyDocumentFilter && anomalyRows.length > 0 && filteredAnomalyRows.length === 0 ? (
            <p className="hint">
              No comparison signals for {anomalyDocumentFilterLabel || "this document"} yet. Clear the
              filter or open the bill and run comparison.
            </p>
          ) : null}
          {anomalyDocumentFilter && anomalyRows.length === 0 && !anomalyListLoading ? (
            <p className="hint">
              No signals loaded. Click <strong>Refresh</strong> after picking a document, or clear the
              filter to see all signals.
            </p>
          ) : null}
        </section>
      )}
      {view === "organizations" && (
        <>
          <section className="card">
            <h2>New workspace</h2>
            <p className="card-subtitle">
              Slug is used in URLs and must look like <code>acme-corp</code>. The scratch label is only for your notes in
              this form.
            </p>
            <label className="field">
              <span>Display name</span>
              <input
                value={orgFormName}
                onChange={(e) => setOrgFormName(e.target.value)}
                placeholder="Acme Corp"
                autoComplete="off"
              />
            </label>
            <label className="field">
              <span>Slug</span>
              <input
                value={orgFormSlug}
                onChange={(e) => setOrgFormSlug(e.target.value)}
                placeholder="acme-corp"
                spellCheck={false}
                autoComplete="off"
              />
            </label>
            <label className="field">
              <span>Scratch label (optional, not sent to API)</span>
              <input value={orgScratchLabel} readOnly placeholder="Click Randomize" className="input-readonly" />
            </label>
            <div className="actions-row">
              <button type="button" className="secondary" onClick={randomizeOrgForm}>
                Randomize
              </button>
              <button type="button" disabled={orgCreateBusy} onClick={() => void submitCreateOrganization()}>
                {orgCreateBusy ? "Creating…" : "Create organization"}
              </button>
            </div>
            {orgCreateMessage && orgCreateMessage.startsWith("Created:") ? (
              <p className="hint org-flash-ok">{orgCreateMessage}</p>
            ) : orgCreateMessage ? (
              <p className="error">{orgCreateMessage}</p>
            ) : null}
          </section>
          <section className="card">
            <div className="doc-list-toolbar">
              <h2>Existing workspaces</h2>
              <button type="button" disabled={orgListLoading} onClick={() => void loadOrganizationsList()}>
                {orgListLoading ? "Loading…" : "Refresh"}
              </button>
            </div>
            <p className="doc-list-lede">Select an organization in the sidebar to activate it, or use the button below.</p>
            {orgListError ? <p className="error">{orgListError}</p> : null}
            {!orgListError && !orgListLoading && orgRows.length === 0 ? <p className="hint">No organizations yet.</p> : null}
            {orgRows.length > 0 ? (
              <div className="table-wrap">
                <table className="doc-table">
                  <thead>
                    <tr>
                      <th>Created</th>
                      <th>Name</th>
                      <th>Slug</th>
                      <th>Your role</th>
                      <th>UUID</th>
                      <th> </th>
                    </tr>
                  </thead>
                  <tbody>
                    {orgRows.map((row) => (
                      <tr key={row.id}>
                        <td>{new Date(row.created_at).toLocaleString()}</td>
                        <td>{row.name}</td>
                        <td className="cell-mono">{row.slug}</td>
                        <td>{row.my_role ?? "—"}</td>
                        <td className="cell-mono cell-id">{row.id}</td>
                        <td>
                          <button type="button" className="secondary table-inline-btn" onClick={() => setOrgId(row.id)}>
                            Select in sidebar
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>

          {/* Sites management — create new sites, view existing */}
          <section className="card">
            <h2>Sites</h2>
            <p className="card-subtitle">
              Sites (locations) let bills at the same location be compared over time. Select an organization
              in the sidebar first, then create sites here.
            </p>
            <p className="hint">
              Bills for the <strong>same site</strong> are compared month over month. Pick a site in the sidebar
              before uploading; assign it on old bills in the document viewer.
            </p>
            {siteListError ? <p className="error">{siteListError}</p> : null}
            <div className="connection-sites-create">
              <label className="field field--inline">
                <span>New site name</span>
                <input
                  value={newSiteName}
                  onChange={(e) => setNewSiteName(e.target.value)}
                  placeholder="Seattle"
                  disabled={!isUuid(effectiveOrgId)}
                />
              </label>
              <button
                type="button"
                className="secondary"
                disabled={!canManageActiveOrg || siteCreateBusy}
                onClick={() => void handleCreateSite()}
              >
                {siteCreateBusy ? "Creating…" : "Create site"}
              </button>
              <button
                type="button"
                className="secondary"
                disabled={!isUuid(effectiveOrgId) || siteListLoading}
                onClick={() => void loadSitesList()}
              >
                Refresh sites
              </button>
            </div>
            {siteCreateMessage ? <p className="hint">{siteCreateMessage}</p> : null}
            {siteRows.length > 0 ? (
              <div className="table-wrap" style={{ marginTop: "0.85rem" }}>
                <table className="doc-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Site ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {siteRows.map((s) => (
                      <tr
                        key={s.id}
                        className={`doc-table__row${selectedSiteId === s.id ? " doc-table__row--selected" : ""}`}
                        onClick={() => {
                          setSelectedSiteId(s.id);
                          if (isUuid(effectiveOrgId)) storeSiteIdForOrg(effectiveOrgId, s.id);
                        }}
                      >
                        <td>
                          {s.name}
                          {selectedSiteId === s.id ? (
                            <span style={{ marginLeft: "0.5rem", fontSize: "0.72rem", color: "var(--ok)" }}>
                              ✓ active
                            </span>
                          ) : null}
                        </td>
                        <td className="cell-mono cell-id">{s.id}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : !siteListLoading && isUuid(effectiveOrgId) ? (
              <p className="hint" style={{ marginTop: "0.5rem" }}>No sites yet for this organization.</p>
            ) : null}
          </section>

          {effectiveOrgId && isUuid(effectiveOrgId) && canManageActiveOrg ? (
            <OrganizationTeamPanel
              apiBase={apiBase}
              organizationId={effectiveOrgId}
              organizationName={orgRows.find((o) => o.id === effectiveOrgId)?.name ?? "Organization"}
            />
          ) : null}
        </>
      )}
          {view === "account" && authUser ? (
            <AccountPage
              apiBase={apiBase}
              user={authUser}
              onUserUpdated={(u) => setAuthUser(u)}
            />
          ) : null}
          {view === "pdf-generator" && platformAdmin ? (
            <PdfGeneratorPage />
          ) : null}
        </div>{/* end .app-content */}

        {/* Review modal portal — rendered at body level */}
        {pendingReview
          ? createPortal(
              <ReviewTransitionModal
                actionLabel={pendingReview.actionLabel}
                note={reviewNoteDraft}
                busy={anomalyReviewBusyId === pendingReview.anomalyId}
                openedAtMs={reviewModalOpenedAtRef.current}
                onNoteChange={setReviewNoteDraft}
                onConfirm={() => void handleConfirmAnomalyReview()}
                onCancel={handleCancelAnomalyReview}
              />,
              document.body,
            )
          : null}
      </main>
    </div>
  );
}
