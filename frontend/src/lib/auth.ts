/**
 * Platform session: register, login + email 2FA, password reset, bearer storage, /auth/me.
 */

const TOKEN_KEY = "spend_integrity_access_token";
const USER_KEY = "spend_integrity_user";
const REMEMBER_DEVICE_KEY = "spend_integrity_remember_device";

export function getRememberDevicePreference(): boolean {
  const v = localStorage.getItem(REMEMBER_DEVICE_KEY);
  if (v === null) return true;
  return v === "true";
}

export function setRememberDevicePreference(remember: boolean): void {
  localStorage.setItem(REMEMBER_DEVICE_KEY, remember ? "true" : "false");
}

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

export type LoginChallengeResponse = {
  message: string;
  challenge_id?: string | null;
  access_token?: string | null;
  token_type?: string;
  user?: AuthUser | null;
};

export function loginChallengeCompletesSession(
  res: LoginChallengeResponse,
): res is LoginChallengeResponse & { access_token: string; user: AuthUser } {
  return Boolean(res.access_token && res.user);
}

export type MessageResponse = {
  message: string;
};

export type RegisterResponse = {
  message: string;
  user: AuthUser;
};

function apiUrl(apiBase: string, path: string): string {
  return `${apiBase.replace(/\/$/, "")}/api/v1${path}`;
}

async function parseError(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const json = JSON.parse(text) as { detail?: string | { msg?: string }[] };
    if (typeof json.detail === "string") return json.detail;
    if (Array.isArray(json.detail) && json.detail[0]?.msg) return json.detail[0].msg;
  } catch {
    /* use raw text */
  }
  return text || `Request failed (${res.status})`;
}

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

export async function register(
  apiBase: string,
  email: string,
  password: string,
): Promise<RegisterResponse> {
  const res = await fetch(apiUrl(apiBase, "/auth/register"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as RegisterResponse;
}

/** Step 1: password check; emails a verification code. */
export async function loginStart(
  apiBase: string,
  email: string,
  password: string,
  rememberDevice = false,
): Promise<LoginChallengeResponse> {
  const res = await fetch(apiUrl(apiBase, "/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, remember_device: rememberDevice }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as LoginChallengeResponse;
}

/** Step 2: verify email OTP and store session. */
export async function loginVerifyOtp(
  apiBase: string,
  challengeId: string,
  code: string,
  rememberDevice = false,
): Promise<LoginResponse> {
  const res = await fetch(apiUrl(apiBase, "/auth/login/verify-2fa"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      challenge_id: challengeId,
      code,
      remember_device: rememberDevice,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data = (await res.json()) as LoginResponse;
  setSession(data);
  return data;
}

/** Sign in: one step when SMTP is off (dev), two steps (OTP) when SMTP is on. */
export async function login(apiBase: string, email: string, password: string): Promise<LoginResponse> {
  const start = await loginStart(apiBase, email, password);
  if (loginChallengeCompletesSession(start)) {
    const data: LoginResponse = {
      access_token: start.access_token,
      token_type: start.token_type ?? "bearer",
      user: start.user,
    };
    setSession(data);
    return data;
  }
  throw new Error("Email verification required — call loginVerifyOtp with the code from your email.");
}

export async function forgotPassword(apiBase: string, email: string): Promise<MessageResponse> {
  const res = await fetch(apiUrl(apiBase, "/auth/forgot-password"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as MessageResponse;
}

export async function resetPassword(
  apiBase: string,
  resetToken: string,
  newPassword: string,
): Promise<MessageResponse> {
  const res = await fetch(apiUrl(apiBase, "/auth/reset-password"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reset_token: resetToken, new_password: newPassword }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as MessageResponse;
}

export async function changePassword(
  apiBase: string,
  currentPassword: string,
  newPassword: string,
): Promise<MessageResponse> {
  const res = await fetch(apiUrl(apiBase, "/auth/change-password"), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as MessageResponse;
}

export async function changeEmail(
  apiBase: string,
  newEmail: string,
  currentPassword: string,
): Promise<LoginResponse> {
  const res = await fetch(apiUrl(apiBase, "/auth/change-email"), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      new_email: newEmail,
      current_password: currentPassword,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data = (await res.json()) as LoginResponse;
  setSession(data);
  return data;
}

export async function fetchMe(apiBase: string): Promise<AuthUser> {
  const res = await fetch(apiUrl(apiBase, "/auth/me"), {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const user = (await res.json()) as AuthUser;
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  return user;
}
