/**
 * Client for document APIs: presigned upload (1b–1c), list + detail (1h, 2a).
 *
 * PUT goes **directly to MinIO/S3** (cross-origin); MinIO must allow the Vite
 * origin (`MINIO_API_CORS_ALLOW_ORIGIN` in docker-compose).
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
  created_at: string;
}

function orgHeaders(orgId: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-Organization-Id": orgId,
  };
}

/** Step 1: ask API for a presigned PUT URL and a pending ``Document`` row. */
export async function presignUpload(
  apiBase: string,
  orgId: string,
  file: File,
): Promise<PresignedUploadResponse> {
  const mime = file.type || "application/octet-stream";
  const res = await fetch(`${apiBase}/api/v1/documents/presigned-upload`, {
    method: "POST",
    headers: orgHeaders(orgId),
    body: JSON.stringify({
      mime_type: mime,
      expected_byte_size: file.size,
    }),
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
    headers: { "X-Organization-Id": orgId },
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
    headers: { "X-Organization-Id": orgId },
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
    headers: { "X-Organization-Id": orgId },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Document fetch failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<DocumentDetailResponse>;
}
