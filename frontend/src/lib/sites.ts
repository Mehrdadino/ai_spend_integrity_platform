import { tenantHeaders, tenantJsonHeaders } from "./api";

/**
 * Org-scoped sites API (locations). Uses bearer token or dev org header.
 */

export interface SiteResponse {
  id: string;
  organization_id: string;
  name: string;
  created_at: string;
}

export async function fetchSitesList(apiBase: string, orgId: string, limit = 200): Promise<SiteResponse[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${apiBase}/api/v1/sites?${params}`, { headers: tenantHeaders(orgId) });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Sites list failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<SiteResponse[]>;
}

export async function createSite(apiBase: string, orgId: string, name: string): Promise<SiteResponse> {
  const res = await fetch(`${apiBase}/api/v1/sites`, {
    method: "POST",
    headers: tenantJsonHeaders(orgId),
    body: JSON.stringify({ name: name.trim() }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Create site failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<SiteResponse>;
}
