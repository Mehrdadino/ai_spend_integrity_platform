/**
 * Dev admin API for tenants: list and create organizations (no ``X-Organization-Id``).
 * Wire the UI ``Organizations`` tab to these routes; production should add auth.
 */
export interface OrganizationResponse {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface CreateOrganizationRequest {
  name: string;
  slug: string;
}

/** List organizations (newest first). */
export async function fetchOrganizationsList(apiBase: string, limit = 200): Promise<OrganizationResponse[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${apiBase}/api/v1/organizations?${params}`);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Organizations list failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<OrganizationResponse[]>;
}

/** Create a tenant; throws with response body on error. */
export async function createOrganization(
  apiBase: string,
  body: CreateOrganizationRequest,
): Promise<OrganizationResponse> {
  const res = await fetch(`${apiBase}/api/v1/organizations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Create organization failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<OrganizationResponse>;
}
