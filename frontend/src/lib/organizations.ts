/**
 * Organizations API (JWT). Admins see all; members see orgs they created.
 */

import { bearerHeaders } from "./api";
import { authHeaders } from "./auth";

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

/** List organizations visible to the signed-in user. */
export async function fetchOrganizationsList(apiBase: string, limit = 200): Promise<OrganizationResponse[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${apiBase}/api/v1/organizations?${params}`, {
    headers: bearerHeaders(),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Organizations list failed (${res.status}): ${body}`);
  }
  return res.json() as Promise<OrganizationResponse[]>;
}

/** Create a tenant (caller becomes owner unless platform admin). */
export async function createOrganization(
  apiBase: string,
  body: CreateOrganizationRequest,
): Promise<OrganizationResponse> {
  const res = await fetch(`${apiBase}/api/v1/organizations`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Create organization failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<OrganizationResponse>;
}
