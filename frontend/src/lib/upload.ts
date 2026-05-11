/**
 * Client for the presigned upload flow (step 1b API + step 1c UI).
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
