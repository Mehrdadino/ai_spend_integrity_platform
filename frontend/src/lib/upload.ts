import { tenantHeaders, tenantJsonHeaders } from "./api";

/**
 * Client for document APIs: presigned upload (1b–1c), list + detail (1h, 2a),
 * and presigned read URLs for in-browser preview (GET ``…/viewer`` / ``read-url``).
 * Normalized bills: ``GET …/bill`` (2d read model).
 *
 * PUT goes **directly to MinIO/S3** (cross-origin); MinIO must allow the Vite
 * origin (`MINIO_API_CORS_ALLOW_ORIGIN` in docker-compose). Presigned GET
 * URLs are also cross-origin when opened in ``iframe`` / ``img``.
 */
export interface PresignedUploadResponse {
  document_id: string;
  bucket: string;
  object_key: string;
  upload_url: string;
  upload_method: string;
  headers: Record<string, string>;
  expires_in_seconds: number;
}

export interface CompleteUploadResponse {
  document_id: string;
  sha256: string;
  byte_size: number;
  processing_status: string;
  processing_error?: string | null;
}

/** Response from ``POST …/reprocess`` (row reset to ``queued`` for the worker). */
export interface ReprocessDocumentResponse {
  document_id: string;
  processing_status: string;
  processing_error?: string | null;
}

export interface DocumentDetailResponse {
  document_id: string;
  organization_id: string;
  site_id: string | null;
  bucket: string;
  object_key: string;
  sha256: string | null;
  mime_type: string;
  byte_size: number | null;
  source: string;
  processing_status: string;
  processing_error?: string | null;
  created_at: string;
  latest_raw_extraction?: RawExtractionSnapshotResponse | null;
}

/** Metadata plus a presigned GET for the stored object (single round-trip for the viewer UI). */
export interface DocumentViewerResponse extends DocumentDetailResponse {
  read_url: string;
  read_url_expires_in_seconds: number;
}

export interface RawExtractionSnapshotResponse {
  extraction_id: string;
  model_id: string | null;
  extraction_version: string | null;
  created_at: string;
  raw_payload: Record<string, unknown>;
}

/** Row from ``GET /api/v1/documents`` (step 1h ingestion list). */
export interface DocumentListItemResponse {
  document_id: string;
  site_id: string | null;
  mime_type: string;
  byte_size: number | null;
  sha256: string | null;
  source: string;
  processing_status: string;
  processing_error?: string | null;
  /** Rollup from ``anomalies.review_status`` (null when no comparison signals). */
  anomaly_review_status?: "open" | "approved" | "dismissed" | "flagged" | null;
  created_at: string;
}

/** One row under ``GET /api/v1/documents/{id}/bill`` (normalized line item). */
export interface BillLineItemResponse {
  id: string;
  position: number;
  raw_label: string;
  canonical_line_kind: string;
  canonical_service_key: string | null;
  quantity: number | null;
  quantity_unit: string | null;
  amount: number | null;
  currency: string;
  extra: Record<string, unknown>;
  created_at: string;
}

/** Normalized bill header + lines (2d). */
export interface BillResponse {
  id: string;
  organization_id: string;
  site_id: string | null;
  document_id: string;
  raw_extraction_id: string | null;
  spend_domain: string;
  spend_kind: string | null;
  issuer_name: string | null;
  period_start: string | null;
  period_end: string | null;
  currency: string;
  total_amount: number | null;
  summary: Record<string, unknown> | null;
  normalization_version: string;
  created_at: string;
  updated_at: string;
  line_items: BillLineItemResponse[];
}

/** ``GET …/bill`` envelope: ``bill`` is null until the worker has materialized 2d rows. */
export interface DocumentBillResponse {
  document_id: string;
  bill: BillResponse | null;
}

/** Prior bills for the same site (§3a). */
export interface DocumentPriorBillsResponse {
  document_id: string;
  site_id: string | null;
  current_bill_id: string | null;
  ordering_note: string;
  prior_bills: BillResponse[];
}

/** One §3b rule hit (persisted as §3d ``anomalies`` when comparison runs). */
export interface ComparisonFindingResponse {
  rule_id: string;
  severity: "info" | "warning" | "critical";
  title: string;
  summary: string;
  evidence: Record<string, unknown>;
}

/** ``GET …/bill/comparison`` — deterministic MoM / fee / header checks; also refreshes §3d rows. */
export interface DocumentComparisonResponse {
  document_id: string;
  bill_id: string | null;
  site_id: string | null;
  rule_pack_version: string;
  compared_to_bill_id: string | null;
  compared_to_period_end: string | null;
  findings: ComparisonFindingResponse[];
}

/** §4 template narrative + confidence (from ``GET /api/v1/anomalies``). */
export interface ExplainabilityResponse {
  explanation: string;
  confidence: "high" | "medium" | "low";
  reasons: string[];
  version: string;
}

/** One persisted comparison signal (``GET /api/v1/anomalies``). */
export interface AnomalyResponse {
  id: string;
  organization_id: string;
  site_id: string | null;
  site_name: string | null;
  document_id: string;
  bill_id: string;
  bill_line_item_id: string | null;
  compared_to_bill_id: string | null;
  rule_pack_version: string;
  rule_id: string;
  period_end: string | null;
  severity: string;
  title: string;
  summary: string;
  evidence: Record<string, unknown>;
  explainability: ExplainabilityResponse;
  review_status: "open" | "approved" | "dismissed" | "flagged";
  latest_review_note?: string | null;
  created_at: string;
  updated_at: string;
}

export type AnomalyReviewStatus = "open" | "approved" | "dismissed" | "flagged";

/** One append-only row from ``GET …/anomalies/{id}/review-events`` (§5b). */
export interface AnomalyReviewEventResponse {
  id: string;
  anomaly_id: string;
  from_status: string;
  to_status: string;
  note: string | null;
  actor_user_id: string | null;
  created_at: string;
}

export interface PatchDocumentSiteResponse {
  document_id: string;
  site_id: string | null;
}

/** Step 1: ask API for a presigned PUT URL and a pending ``Document`` row. */
export async function presignUpload(
  apiBase: string,
  orgId: string,
  file: File,
  siteId?: string | null,
): Promise<PresignedUploadResponse> {
  const mime = file.type || "application/octet-stream";
  const body: Record<string, unknown> = {
    mime_type: mime,
    expected_byte_size: file.size,
  };
  if (siteId && siteId.trim()) {
    body.site_id = siteId.trim();
  }
  const res = await fetch(`${apiBase}/api/v1/documents/presigned-upload`, {
    method: "POST",
    headers: tenantJsonHeaders(orgId),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Presign failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<PresignedUploadResponse>;
}

/**
 * Step 2: upload bytes to the presigned URL.
 * Uses XHR for ``upload.onprogress`` (fetch upload progress is awkward).
 */
export function putFileToPresignedUrl(
  file: File,
  uploadUrl: string,
  signedHeaders: Record<string, string>,
  onProgress: (loaded: number, total: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", uploadUrl);
    for (const [key, value] of Object.entries(signedHeaders)) {
      xhr.setRequestHeader(key, value);
    }
    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) {
        onProgress(ev.loaded, ev.total);
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error(`Storage PUT failed (${xhr.status}): ${xhr.responseText || xhr.statusText}`));
      }
    };
    xhr.onerror = () => reject(new Error("Network error during storage upload"));
    xhr.send(file);
  });
}

/** Step 3: tell API to hash the object in storage and mark the row ready. */
export async function completeUpload(
  apiBase: string,
  orgId: string,
  documentId: string,
): Promise<CompleteUploadResponse> {
  const res = await fetch(`${apiBase}/api/v1/documents/${documentId}/complete-upload`, {
    method: "POST",
    headers: tenantHeaders(orgId),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Complete failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<CompleteUploadResponse>;
}

/** List documents for the org (newest first); used by ingestion status UI (step 1h). */
export async function fetchDocumentsList(
  apiBase: string,
  orgId: string,
  limit = 100,
): Promise<DocumentListItemResponse[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${apiBase}/api/v1/documents?${params}`, {
    headers: tenantHeaders(orgId),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Documents list failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<DocumentListItemResponse[]>;
}

/** Fetch document metadata (same-org scoped) for the detail panel. */
export async function fetchDocumentDetail(
  apiBase: string,
  orgId: string,
  documentId: string,
): Promise<DocumentDetailResponse> {
  const res = await fetch(`${apiBase}/api/v1/documents/${documentId}`, {
    headers: tenantHeaders(orgId),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Document fetch failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<DocumentDetailResponse>;
}

/** Metadata + presigned read URL for preview (requires finalized upload / stored object). */
export async function fetchDocumentViewer(
  apiBase: string,
  orgId: string,
  documentId: string,
): Promise<DocumentViewerResponse> {
  const res = await fetch(`${apiBase}/api/v1/documents/${documentId}/viewer`, {
    headers: tenantHeaders(orgId),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Document viewer failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<DocumentViewerResponse>;
}

/** Normalized bill for the document viewer (same-org scoped); ``bill`` may be null. */
export async function fetchDocumentBill(
  apiBase: string,
  orgId: string,
  documentId: string,
): Promise<DocumentBillResponse> {
  const res = await fetch(`${apiBase}/api/v1/documents/${documentId}/bill`, {
    headers: tenantHeaders(orgId),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Document bill failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<DocumentBillResponse>;
}

/** Run §3b comparison rules for the current bill vs immediate prior. */
export async function fetchDocumentComparison(
  apiBase: string,
  orgId: string,
  documentId: string,
): Promise<DocumentComparisonResponse> {
  let res: Response;
  try {
    res = await fetch(`${apiBase}/api/v1/documents/${documentId}/bill/comparison`, {
      headers: tenantHeaders(orgId),
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    throw new Error(
      `Bill comparison request failed (${msg}). Check API URL, CORS, and that the backend is running.`,
    );
  }
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Bill comparison failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<DocumentComparisonResponse>;
}

export interface MaterializeComparisonsResponse {
  attempted: number;
  succeeded: number;
  failed: number;
}

/** Batch §3b/§3d for extracted docs with bills (Anomalies tab Refresh — no per-doc viewer). */
export async function postMaterializeAnomalyComparisons(
  apiBase: string,
  orgId: string,
  opts?: { siteId?: string | null; limit?: number },
): Promise<MaterializeComparisonsResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(opts?.limit ?? 500));
  if (opts?.siteId) {
    params.set("site_id", opts.siteId);
  }
  const res = await fetch(`${apiBase}/api/v1/anomalies/materialize-comparisons?${params}`, {
    method: "POST",
    headers: tenantHeaders(orgId),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Materialize comparisons failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<MaterializeComparisonsResponse>;
}

/** §3d anomaly inbox; §5c optional ``reviewStatus`` / sort. */
export async function fetchAnomaliesList(
  apiBase: string,
  orgId: string,
  opts?: {
    siteId?: string | null;
    reviewStatus?: AnomalyReviewStatus | "" | null;
    sort?: "created_at" | "updated_at" | "severity";
    order?: "asc" | "desc";
    limit?: number;
  },
): Promise<AnomalyResponse[]> {
  const params = new URLSearchParams({ limit: String(opts?.limit ?? 100) });
  if (opts?.siteId) {
    params.set("site_id", opts.siteId);
  }
  if (opts?.reviewStatus) {
    params.set("review_status", opts.reviewStatus);
  }
  params.set("sort", opts?.sort ?? "created_at");
  params.set("order", opts?.order ?? "desc");
  const res = await fetch(`${apiBase}/api/v1/anomalies?${params}`, {
    headers: tenantHeaders(orgId),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Anomalies list failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<AnomalyResponse[]>;
}

/** Single anomaly + §4 explainability (detail drawer). */
export async function fetchAnomaly(apiBase: string, orgId: string, anomalyId: string): Promise<AnomalyResponse> {
  const res = await fetch(`${apiBase}/api/v1/anomalies/${anomalyId}`, {
    headers: tenantHeaders(orgId),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Anomaly fetch failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<AnomalyResponse>;
}

/** §5a: transition review state (audit row on server). */
export async function postAnomalyReview(
  apiBase: string,
  orgId: string,
  anomalyId: string,
  body: { to_status: AnomalyReviewStatus; note?: string | null },
): Promise<AnomalyResponse> {
  const res = await fetch(`${apiBase}/api/v1/anomalies/${anomalyId}/review`, {
    method: "POST",
    headers: tenantJsonHeaders(orgId),
    body: JSON.stringify({ to_status: body.to_status, note: body.note ?? null }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Review transition failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<AnomalyResponse>;
}

/** §5b: audit history for one anomaly (notes from §5e transitions). */
export async function fetchAnomalyReviewEvents(
  apiBase: string,
  orgId: string,
  anomalyId: string,
): Promise<AnomalyReviewEventResponse[]> {
  const res = await fetch(`${apiBase}/api/v1/anomalies/${anomalyId}/review-events`, {
    headers: tenantHeaders(orgId),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Review events failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<AnomalyReviewEventResponse[]>;
}

/** Older bills for the same site (§3a). */
export async function fetchDocumentPriorBills(
  apiBase: string,
  orgId: string,
  documentId: string,
  limit = 10,
): Promise<DocumentPriorBillsResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${apiBase}/api/v1/documents/${documentId}/bill/prior-bills?${params}`, {
    headers: tenantHeaders(orgId),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Prior bills failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<DocumentPriorBillsResponse>;
}

/** Set or clear ``site_id`` on a document (and its bill). */
export async function patchDocumentSite(
  apiBase: string,
  orgId: string,
  documentId: string,
  siteId: string | null,
): Promise<PatchDocumentSiteResponse> {
  const res = await fetch(`${apiBase}/api/v1/documents/${documentId}/site`, {
    method: "PATCH",
    headers: tenantJsonHeaders(orgId),
    body: JSON.stringify({ site_id: siteId }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Assign site failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<PatchDocumentSiteResponse>;
}

/** Soft-delete document (sets ``deleted_at``; hidden from list/viewer). */
export async function deleteDocument(
  apiBase: string,
  orgId: string,
  documentId: string,
): Promise<{ document_id: string; deleted_at: string }> {
  const res = await fetch(`${apiBase}/api/v1/documents/${documentId}`, {
    method: "DELETE",
    headers: tenantJsonHeaders(orgId),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Delete document failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<{ document_id: string; deleted_at: string }>;
}

/** Re-queue extraction + bill sync for a finalized document (``extracted`` / ``failed`` / ``received``). */
export async function reprocessDocument(
  apiBase: string,
  orgId: string,
  documentId: string,
): Promise<ReprocessDocumentResponse> {
  const res = await fetch(`${apiBase}/api/v1/documents/${documentId}/reprocess`, {
    method: "POST",
    headers: tenantHeaders(orgId),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Reprocess failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<ReprocessDocumentResponse>;
}
