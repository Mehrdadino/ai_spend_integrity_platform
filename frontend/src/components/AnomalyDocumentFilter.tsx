/**
 * Searchable, paginated document picker for the anomalies inbox (large orgs).
 * Uses ``GET /api/v1/documents/browse`` (20 per page; optional name/UUID filter).
 */

import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  fetchDocumentsBrowse,
  type DocumentListItemResponse,
} from "../lib/upload";

const PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 350;

function documentPickerLabel(row: DocumentListItemResponse): string {
  const name = row.display_name?.trim();
  if (name) {
    return name;
  }
  return `Bill ${row.document_id.slice(0, 8)}…`;
}

export function AnomalyDocumentFilter({
  apiBase,
  orgId,
  value,
  selectedLabel,
  onChange,
  /** When true, blocks opening the picker (e.g. missing org); search stays editable while loading. */
  openDisabled,
}: {
  apiBase: string;
  orgId: string;
  value: string;
  selectedLabel: string;
  onChange: (documentId: string, label: string) => void;
  openDisabled?: boolean;
}) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const skipSearchDebounceRef = useRef(false);
  const [open, setOpen] = useState(false);
  const [searchDraft, setSearchDraft] = useState("");
  const [searchApplied, setSearchApplied] = useState("");
  const [page, setPage] = useState(0);
  const [items, setItems] = useState<DocumentListItemResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPage = useCallback(
    async (q: string, pageIndex: number) => {
      if (!apiBase.trim() || !orgId.trim()) {
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const res = await fetchDocumentsBrowse(apiBase.trim(), orgId, {
          q: q.trim() || undefined,
          offset: pageIndex * PAGE_SIZE,
          limit: PAGE_SIZE,
        });
        setItems(res.items);
        setTotal(res.total);
        setPage(pageIndex);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setItems([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    },
    [apiBase, orgId],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    if (skipSearchDebounceRef.current) {
      skipSearchDebounceRef.current = false;
      return;
    }
    const handle = window.setTimeout(() => {
      setSearchApplied(searchDraft);
      void loadPage(searchDraft, 0);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [searchDraft, open, loadPage]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onDocClick = (ev: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(ev.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageStart = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const pageEnd = Math.min(total, (page + 1) * PAGE_SIZE);

  const openPicker = () => {
    if (openDisabled) {
      return;
    }
    skipSearchDebounceRef.current = true;
    setOpen(true);
    setSearchDraft("");
    setSearchApplied("");
    void loadPage("", 0);
  };

  return (
    <div className="anomaly-doc-filter" ref={rootRef}>
      <span className="anomaly-doc-filter__label" id={`${listId}-label`}>
        Document
      </span>
      <div className="anomaly-doc-filter__control">
        {value ? (
          <div className="anomaly-doc-filter__selected">
            <span className="anomaly-doc-filter__selected-name" title={value}>
              {selectedLabel || value}
            </span>
            <button
              type="button"
              className="secondary anomaly-doc-filter__clear"
              disabled={openDisabled}
              onClick={() => onChange("", "")}
            >
              Clear
            </button>
            <button
              type="button"
              className="secondary"
              disabled={openDisabled}
              onClick={() => openPicker()}
            >
              Change…
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="secondary anomaly-doc-filter__all"
            disabled={openDisabled}
            onClick={() => openPicker()}
          >
            All documents — filter by bill…
          </button>
        )}
        {open ? (
          <div
            className="anomaly-doc-filter__panel card card--nested"
            role="dialog"
            aria-labelledby={`${listId}-label`}
          >
            <label className="field anomaly-doc-filter__search">
              <span className="sr-only">Search by name or document UUID</span>
              <input
                type="search"
                value={searchDraft}
                placeholder="Search name or document UUID…"
                autoFocus
                onChange={(e) => setSearchDraft(e.target.value)}
              />
            </label>
            {searchApplied.trim() ? (
              <p className="hint anomaly-doc-filter__hint">
                Filtering by “{searchApplied.trim()}”. Clear the box to browse all documents.
              </p>
            ) : (
              <p className="hint anomaly-doc-filter__hint">
                Showing newest uploads, {PAGE_SIZE} per page ({total.toLocaleString()} total).
              </p>
            )}
            {error ? <p className="error">{error}</p> : null}
            {loading && items.length === 0 ? (
              <p className="hint">Loading documents…</p>
            ) : null}
            {!loading && items.length === 0 && !error ? (
              <p className="hint">No documents match.</p>
            ) : null}
            {items.length > 0 ? (
              <ul className="anomaly-doc-filter__list" role="listbox" aria-label="Documents">
                {items.map((row) => (
                  <li key={row.document_id}>
                    <button
                      type="button"
                      className={`anomaly-doc-filter__option${value === row.document_id ? " anomaly-doc-filter__option--active" : ""}`}
                      role="option"
                      aria-selected={value === row.document_id}
                      onClick={() => {
                        onChange(row.document_id, documentPickerLabel(row));
                        setOpen(false);
                      }}
                    >
                      <span className="anomaly-doc-filter__option-name">
                        {documentPickerLabel(row)}
                      </span>
                      <span className="anomaly-doc-filter__option-meta">
                        <code>{row.document_id}</code>
                        <span> · {new Date(row.created_at).toLocaleDateString()}</span>
                        <span> · {row.processing_status}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            <div className="anomaly-doc-filter__pager">
              <button
                type="button"
                className="secondary"
                disabled={loading || page <= 0}
                onClick={() => void loadPage(searchApplied, page - 1)}
              >
                Previous
              </button>
              <span className="hint anomaly-doc-filter__page-info">
                {total === 0
                  ? "No results"
                  : `${pageStart}–${pageEnd} of ${total.toLocaleString()} · page ${page + 1} of ${pageCount}`}
              </span>
              <button
                type="button"
                className="secondary"
                disabled={loading || page + 1 >= pageCount}
                onClick={() => void loadPage(searchApplied, page + 1)}
              >
                Next
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
