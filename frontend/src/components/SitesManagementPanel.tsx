/**
 * Sites (locations) for one organization: list, create, and pick the active site.
 * Shown on the Sites tab; sidebar site selector stays in App shell.
 */

import type { SiteResponse } from "../lib/sites";

export type SitesManagementPanelProps = {
  organizationName: string | null;
  /** True when a valid org UUID is selected in the sidebar. */
  organizationReady: boolean;
  /** Org admin (or platform admin) may create sites. */
  canManage: boolean;
  sites: SiteResponse[];
  listLoading: boolean;
  listError: string | null;
  selectedSiteId: string;
  newSiteName: string;
  onNewSiteNameChange: (value: string) => void;
  createBusy: boolean;
  createMessage: string | null;
  onCreate: () => void;
  onRefresh: () => void;
  onSelectSite: (siteId: string) => void;
};

export function SitesManagementPanel({
  organizationName,
  organizationReady,
  canManage,
  sites,
  listLoading,
  listError,
  selectedSiteId,
  newSiteName,
  onNewSiteNameChange,
  createBusy,
  createMessage,
  onCreate,
  onRefresh,
  onSelectSite,
}: SitesManagementPanelProps) {
  return (
    <>
      <section className="card">
        <h2>Sites</h2>
        <p className="card-subtitle">
          Sites are locations within an organization. Bills for the same site are compared month over
          month. Select an organization in the sidebar, then create and manage sites here.
        </p>
        {!organizationReady ? (
          <p className="hint">Select an organization in the sidebar to view and create sites.</p>
        ) : (
          <p className="hint">
            Active organization: <strong>{organizationName ?? "Organization"}</strong>. The site you
            pick here also updates the sidebar selector used for uploads.
          </p>
        )}
        <p className="hint">
          Pick a site in the sidebar before uploading; assign sites on older bills in the document
          viewer.
        </p>
        {listError ? <p className="error">{listError}</p> : null}
        <div className="connection-sites-create">
          <label className="field field--inline">
            <span>New site name</span>
            <input
              value={newSiteName}
              onChange={(e) => onNewSiteNameChange(e.target.value)}
              placeholder="Seattle"
              disabled={!organizationReady}
            />
          </label>
          <button
            type="button"
            className="secondary"
            disabled={!canManage || createBusy}
            onClick={() => onCreate()}
          >
            {createBusy ? "Creating…" : "Create site"}
          </button>
          <button
            type="button"
            className="secondary"
            disabled={!organizationReady || listLoading}
            onClick={() => onRefresh()}
          >
            {listLoading ? "Loading…" : "Refresh"}
          </button>
        </div>
        {createMessage ? <p className="hint">{createMessage}</p> : null}
        {sites.length > 0 ? (
          <div className="table-wrap" style={{ marginTop: "0.85rem" }}>
            <table className="doc-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Site ID</th>
                </tr>
              </thead>
              <tbody>
                {sites.map((s) => (
                  <tr
                    key={s.id}
                    className={`doc-table__row${selectedSiteId === s.id ? " doc-table__row--selected" : ""}`}
                    onClick={() => onSelectSite(s.id)}
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
        ) : !listLoading && organizationReady ? (
          <p className="hint" style={{ marginTop: "0.5rem" }}>
            No sites yet for this organization.
          </p>
        ) : null}
      </section>
    </>
  );
}
