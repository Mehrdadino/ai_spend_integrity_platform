/**
 * Org-scoped sites API (locations). Requires ``X-Organization-Id`` on every call.
 */

export interface SiteResponse {
  id: string;
  organization_id: string;
  name: string;
  created_at: string;
}

function orgHeaders(orgId: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-Organization-Id": orgId,
  };
}

export async function fetchSitesList(apiBase: string, orgId: string, limit = 200): Promise<SiteResponse[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${apiBase}/api/v1/sites?${params}`, { headers: orgHeaders(orgId) });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Sites list failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<SiteResponse[]>;
}

export async function createSite(apiBase: string, orgId: string, name: string): Promise<SiteResponse> {
  const res = await fetch(`${apiBase}/api/v1/sites`, {
    method: "POST",
    headers: orgHeaders(orgId),
    body: JSON.stringify({ name: name.trim() }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Create site failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<SiteResponse>;
}
