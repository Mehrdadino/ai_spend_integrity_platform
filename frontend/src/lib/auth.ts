/**
 * Platform session: login (email/password only), bearer storage, /auth/me.
 */

const TOKEN_KEY = "spend_integrity_access_token";
const USER_KEY = "spend_integrity_user";

export type AuthUser = {
  id: string;
  organization_id: string | null;
  email: string;
  role: string;
  created_at: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

export function getAccessToken(): string | null {
  const v = localStorage.getItem(TOKEN_KEY);
  return v && v.length > 0 ? v : null;
}

export function getStoredUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function setSession(login: LoginResponse): void {
  localStorage.setItem(TOKEN_KEY, login.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(login.user));
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function isPlatformAdmin(user: AuthUser | null): boolean {
  return user?.role === "admin";
}

export function authHeaders(): HeadersInit {
  const token = getAccessToken();
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

export async function login(apiBase: string, email: string, password: string): Promise<LoginResponse> {
  const res = await fetch(`${apiBase.replace(/\/$/, "")}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Sign in failed (${res.status}): ${text}`);
  }
  const data = (await res.json()) as LoginResponse;
  setSession(data);
  return data;
}

export async function fetchMe(apiBase: string): Promise<AuthUser> {
  const res = await fetch(`${apiBase.replace(/\/$/, "")}/api/v1/auth/me`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Session check failed (${res.status}): ${text}`);
  }
  const user = (await res.json()) as AuthUser;
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  return user;
}
