/**
 * Organization team: members and invites (org admin).
 */

import { authHeaders } from "./auth";

export type OrganizationMemberResponse = {
  user_id: string;
  email: string;
  role: string;
  created_at: string;
};

export type OrganizationInviteResponse = {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  created_at: string;
};

export type AcceptInviteResponse = {
  organization_id: string;
  organization_name: string;
  role: string;
  message: string;
};

function orgUrl(apiBase: string, orgId: string, path: string): string {
  return `${apiBase.replace(/\/$/, "")}/api/v1/organizations/${orgId}${path}`;
}

async function parseError(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const json = JSON.parse(text) as { detail?: string };
    if (typeof json.detail === "string") return json.detail;
  } catch {
    /* raw */
  }
  return text || `Request failed (${res.status})`;
}

export async function fetchOrganizationMembers(
  apiBase: string,
  organizationId: string,
): Promise<OrganizationMemberResponse[]> {
  const res = await fetch(orgUrl(apiBase, organizationId, "/members"), {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as OrganizationMemberResponse[];
}

export async function fetchOrganizationInvites(
  apiBase: string,
  organizationId: string,
): Promise<OrganizationInviteResponse[]> {
  const res = await fetch(orgUrl(apiBase, organizationId, "/invites"), {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as OrganizationInviteResponse[];
}

export async function createOrganizationInvite(
  apiBase: string,
  organizationId: string,
  email: string,
  role: string,
): Promise<OrganizationInviteResponse> {
  const res = await fetch(orgUrl(apiBase, organizationId, "/invites"), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ email, role }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as OrganizationInviteResponse;
}

export async function updateOrganizationMemberRole(
  apiBase: string,
  organizationId: string,
  userId: string,
  role: string,
): Promise<OrganizationMemberResponse> {
  const res = await fetch(orgUrl(apiBase, organizationId, `/members/${userId}`), {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ role }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as OrganizationMemberResponse;
}

export async function removeOrganizationMember(
  apiBase: string,
  organizationId: string,
  userId: string,
): Promise<void> {
  const res = await fetch(orgUrl(apiBase, organizationId, `/members/${userId}`), {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function acceptOrganizationInvite(
  apiBase: string,
  inviteToken: string,
): Promise<AcceptInviteResponse> {
  const res = await fetch(`${apiBase.replace(/\/$/, "")}/api/v1/auth/accept-invite`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ invite_token: inviteToken }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as AcceptInviteResponse;
}

export function isOrgAdminRole(role: string | null | undefined): boolean {
  return role === "org_admin";
}

export function canWriteOrgRole(role: string | null | undefined): boolean {
  return role === "org_admin" || role === "member";
}
