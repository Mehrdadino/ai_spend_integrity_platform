/**
 * Shared API headers: JWT bearer + optional active organization.
 */

import { authHeaders, getAccessToken } from "./auth";

/** Bearer token only (organization list, login follow-up). */
export function bearerHeaders(): HeadersInit {
  return authHeaders();
}

/** Active tenant for document/anomaly/site routes. */
export function tenantHeaders(orgId: string): HeadersInit {
  const headers: Record<string, string> = { ...authHeaders() } as Record<string, string>;
  const token = getAccessToken();
  if (!token && orgId.trim()) {
    headers["X-Organization-Id"] = orgId.trim();
  } else if (orgId.trim()) {
    headers["X-Organization-Id"] = orgId.trim();
  }
  return headers;
}

export function tenantJsonHeaders(orgId: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...tenantHeaders(orgId),
  };
}
