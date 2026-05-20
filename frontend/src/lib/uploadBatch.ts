/**
 * Multi-file upload helper for the Upload tab (presign → PUT → complete per file).
 *
 * Each file is a separate document row and worker job. Batches are processed
 * **sequentially** to keep progress readable and avoid hammering extraction at once.
 */

import {
  completeUpload,
  MAX_UPLOAD_BATCH_SIZE,
  MAX_UPLOAD_FILE_BYTES,
  presignUpload,
  putFileToPresignedUrl,
  type CompleteUploadResponse,
  type PresignUploadOptions,
} from "./upload";

export { MAX_UPLOAD_BATCH_SIZE, MAX_UPLOAD_FILE_BYTES } from "./upload";

export type UploadBatchItemStatus =
  | "pending"
  | "presigning"
  | "uploading"
  | "completing"
  | "done"
  | "error";

export interface UploadBatchItem {
  /** Stable key for React lists (index-based id). */
  key: string;
  file: File;
  status: UploadBatchItemStatus;
  progressPct: number;
  message: string;
  result?: CompleteUploadResponse;
}

export type UploadBatchProgress = {
  items: UploadBatchItem[];
  /** 0–100 across the whole batch. */
  overallPct: number;
  currentIndex: number;
  total: number;
};

function isPdfFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return file.type === "application/pdf" || name.endsWith(".pdf");
}

/**
 * Validate and cap a ``FileList`` from ``<input type="file" multiple>``.
 */
export function normalizeSelectedPdfFiles(fileList: FileList | null): {
  files: File[];
  warnings: string[];
} {
  const warnings: string[] = [];
  if (!fileList || fileList.length === 0) {
    return { files: [], warnings };
  }

  const raw = Array.from(fileList);
  const pdfs = raw.filter(isPdfFile);
  if (pdfs.length < raw.length) {
    warnings.push("Non-PDF files were skipped (only PDF utility invoices are supported).");
  }

  const sized: File[] = [];
  for (const f of pdfs) {
    if (f.size > MAX_UPLOAD_FILE_BYTES) {
      const mb = (MAX_UPLOAD_FILE_BYTES / (1024 * 1024)).toFixed(0);
      warnings.push(`"${f.name}" exceeds ${mb} MB and was skipped.`);
      continue;
    }
    if (f.size === 0) {
      warnings.push(`"${f.name}" is empty and was skipped.`);
      continue;
    }
    sized.push(f);
  }

  if (sized.length > MAX_UPLOAD_BATCH_SIZE) {
    warnings.push(
      `Only the first ${MAX_UPLOAD_BATCH_SIZE} files are kept (maximum per upload).`,
    );
    return { files: sized.slice(0, MAX_UPLOAD_BATCH_SIZE), warnings };
  }

  return { files: sized, warnings };
}

function initialItems(files: File[]): UploadBatchItem[] {
  return files.map((file, i) => ({
    key: `${i}-${file.name}-${file.size}-${file.lastModified}`,
    file,
    status: "pending",
    progressPct: 0,
    message: "Waiting…",
  }));
}

function patchItem(
  items: UploadBatchItem[],
  key: string,
  patch: Partial<UploadBatchItem>,
): UploadBatchItem[] {
  return items.map((it) => (it.key === key ? { ...it, ...patch } : it));
}

function overallPct(items: UploadBatchItem[], currentIndex: number, total: number): number {
  if (total === 0) {
    return 0;
  }
  const done = items.filter((it) => it.status === "done" || it.status === "error").length;
  const active = items[currentIndex];
  const activeShare =
    active && (active.status === "uploading" || active.status === "completing")
      ? active.progressPct / 100 / total
      : 0;
  return Math.min(100, Math.round(((done + activeShare) / total) * 100));
}

/**
 * Upload each file in order; invokes ``onProgress`` after every item update.
 */
export async function runUploadBatch(params: {
  apiBase: string;
  orgId: string;
  files: File[];
  /** Applied only when ``files.length === 1`` (same as single-file upload). */
  displayName?: string | null;
  siteId?: string | null;
  onProgress: (state: UploadBatchProgress) => void;
}): Promise<UploadBatchItem[]> {
  const { apiBase, orgId, files, displayName, siteId, onProgress } = params;
  const total = files.length;
  let items = initialItems(files);
  const presignOptions: PresignUploadOptions =
    files.length === 1
      ? {
          siteId: siteId?.trim() || null,
          displayName: displayName?.trim() || null,
        }
      : { siteId: siteId?.trim() || null };

  onProgress({ items, overallPct: 0, currentIndex: 0, total });

  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    const key = items[i].key;

    const emit = (patch: Partial<UploadBatchItem>) => {
      items = patchItem(items, key, patch);
      onProgress({ items, overallPct: overallPct(items, i, total), currentIndex: i, total });
    };

    try {
      emit({ status: "presigning", progressPct: 0, message: "Requesting presigned upload…" });
      const presign = await presignUpload(apiBase.trim(), orgId, file, presignOptions);

      emit({ status: "uploading", progressPct: 0, message: "Uploading to object storage…" });
      await putFileToPresignedUrl(file, presign.upload_url, presign.headers, (loaded, putTotal) => {
        const pct = putTotal > 0 ? Math.round((100 * loaded) / putTotal) : 0;
        emit({ status: "uploading", progressPct: pct, message: `Uploading… ${pct}%` });
      });

      emit({ status: "completing", progressPct: 92, message: "Finalizing (server-side hash)…" });
      const result = await completeUpload(apiBase.trim(), orgId, presign.document_id);
      emit({
        status: "done",
        progressPct: 100,
        message: "Complete",
        result,
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      emit({
        status: "error",
        progressPct: 0,
        message: msg,
      });
    }
  }

  return items;
}

export function batchSummary(items: UploadBatchItem[]): {
  succeeded: number;
  failed: number;
  total: number;
} {
  const succeeded = items.filter((it) => it.status === "done").length;
  const failed = items.filter((it) => it.status === "error").length;
  return { succeeded, failed, total: items.length };
}
