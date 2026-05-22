/**
 * §3c cross-site comparison: user picks which other sites to compare against this bill.
 *
 * Searchable checkbox list (scales better than a single dropdown for multi-select).
 */

import { useMemo, useState } from "react";
import type { DocumentComparisonResponse } from "../lib/upload";

export interface SiteOption {
  id: string;
  name: string;
}

export interface PeerSitesConfig {
  document_id: string;
  anchor_site_id: string | null;
  saved_peer_site_ids: string[];
  available_sites: SiteOption[];
}

function comparisonSeverityLabel(severity: string): string {
  if (severity === "critical") return "Critical";
  if (severity === "warning") return "Warning";
  return "Info";
}

type Props = {
  config: PeerSitesConfig | null;
  configLoading: boolean;
  configError: string | null;
  selectedSiteIds: string[];
  onSelectedSiteIdsChange: (ids: string[]) => void;
  peerComparison: DocumentComparisonResponse | null | undefined;
  peerLoading: boolean;
  peerError: string | null;
  onRun: (useAutoPeers: boolean) => void;
  onViewSignals?: () => void;
  disabled?: boolean;
};

export function CrossSitePeerPanel({
  config,
  configLoading,
  configError,
  selectedSiteIds,
  onSelectedSiteIdsChange,
  peerComparison,
  peerLoading,
  peerError,
  onRun,
  onViewSignals,
  disabled,
}: Props) {
  const [search, setSearch] = useState("");

  const peerSites = useMemo(() => {
    if (!config) return [];
    const anchor = config.anchor_site_id;
    return config.available_sites.filter((s) => s.id !== anchor);
  }, [config]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return peerSites;
    return peerSites.filter((s) => s.name.toLowerCase().includes(q));
  }, [peerSites, search]);

  function toggleSite(siteId: string, checked: boolean) {
    if (checked) {
      onSelectedSiteIdsChange([...selectedSiteIds, siteId]);
    } else {
      onSelectedSiteIdsChange(selectedSiteIds.filter((id) => id !== siteId));
    }
  }

  function selectAllVisible() {
    const ids = new Set(selectedSiteIds);
    for (const s of filtered) {
      ids.add(s.id);
    }
    onSelectedSiteIdsChange([...ids]);
  }

  function clearSelection() {
    onSelectedSiteIdsChange([]);
  }

  return (
    <div className="comparison-section peer-sites-section" aria-live="polite">
      <div className="comparison-section__head">
        <h4 className="comparison-title">Cross-site comparison</h4>
        {onViewSignals ? (
          <button type="button" className="secondary comparison-inbox-link" onClick={onViewSignals}>
            View in signals inbox
          </button>
        ) : null}
      </div>
      <p className="comparison-note">
        Choose which <strong>other locations</strong> should be compared to this bill (same billing
        month and utility type). Leave none selected and use <strong>Auto-discover peers</strong> to
        let the system pick similar sites, or pick at least one site and run a targeted compare.
        {peerComparison?.rule_pack_version ? (
          <>
            {" "}
            <span className="cell-mono">({peerComparison.rule_pack_version})</span>
          </>
        ) : null}
      </p>

      {configError ? <p className="error">{configError}</p> : null}
      {configLoading ? <p className="hint">Loading sites…</p> : null}

      {!configLoading && config && !config.anchor_site_id ? (
        <p className="hint">Assign a site to this document before cross-site comparison.</p>
      ) : null}

      {!configLoading && config?.anchor_site_id ? (
        <>
          <label className="field peer-sites-search">
            <span>Search sites</span>
            <input
              type="search"
              placeholder="Filter by name…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              disabled={disabled}
            />
          </label>

          <div className="peer-sites-toolbar">
            <button type="button" className="secondary" onClick={selectAllVisible} disabled={disabled}>
              Select all
            </button>
            <button type="button" className="secondary" onClick={clearSelection} disabled={disabled}>
              Clear
            </button>
            <span className="hint peer-sites-count">
              {selectedSiteIds.length} selected
              {peerSites.length > 0 ? ` · ${peerSites.length} other site(s) in org` : ""}
            </span>
          </div>

          <ul className="peer-sites-list" role="group" aria-label="Peer sites to compare">
            {filtered.length === 0 ? (
              <li className="hint">No sites match your search.</li>
            ) : (
              filtered.map((site) => {
                const checked = selectedSiteIds.includes(site.id);
                return (
                  <li key={site.id}>
                    <label className="peer-sites-list__item">
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={disabled}
                        onChange={(e) => toggleSite(site.id, e.target.checked)}
                      />
                      <span>{site.name}</span>
                    </label>
                  </li>
                );
              })
            )}
          </ul>

          <div className="peer-sites-actions">
            <button
              type="button"
              onClick={() => onRun(false)}
              disabled={disabled || peerLoading || selectedSiteIds.length === 0}
            >
              {peerLoading ? "Comparing…" : "Compare with selected sites"}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => onRun(true)}
              disabled={disabled || peerLoading}
            >
              Auto-discover peers
            </button>
          </div>
        </>
      ) : null}

      {peerError ? <p className="error">{peerError}</p> : null}
      {peerLoading ? (
        <p className="comparison-loading">
          <span className="pipeline-spinner pipeline-spinner--inline" aria-hidden />
          Running cross-site comparison…
        </p>
      ) : null}

      {!peerLoading && peerComparison && peerComparison.findings.length > 0 ? (
        <ul className="comparison-findings">
          {peerComparison.findings.map((f) => (
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
      {!peerLoading &&
      peerComparison &&
      peerComparison.findings.length === 0 &&
      peerComparison.rule_pack_version ? (
        <p className="comparison-empty">No cross-site signals for this run.</p>
      ) : null}
    </div>
  );
}
