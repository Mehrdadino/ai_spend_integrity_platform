/**
 * Auth gate: sign-in (email + optional 2FA), create account, forgot/reset password.
 * Layout: split-screen with branded panel on left, form on right.
 */

import { useEffect, useMemo, useState } from "react";
import { PasswordPolicyHints } from "./components/PasswordPolicyHints";
import { isPasswordAcceptable } from "./lib/passwordPolicy";
import {
  forgotPassword,
  loginChallengeCompletesSession,
  loginStart,
  loginVerifyOtp,
  activateInvite,
  fetchInvitePreview,
  register,
  resetPassword,
  getRememberDevicePreference,
  setRememberDevicePreference,
  setSession,
  type AuthUser,
  type OrganizationInvitePreview,
} from "./lib/auth";

const defaultApiBase = "http://127.0.0.1:8000";

type AuthView =
  | "sign-in"
  | "create-account"
  | "verify-2fa"
  | "forgot-password"
  | "reset-password"
  | "accept-invite";

export type SignedInContext = {
  organizationId?: string;
};

type LoginPageProps = {
  initialApiBase?: string;
  resetToken?: string | null;
  inviteToken?: string | null;
  onSignedIn: (user: AuthUser, apiBase: string, ctx?: SignedInContext) => void;
};

function clearInviteTokenFromUrl(): void {
  const url = new URL(window.location.href);
  if (!url.searchParams.has("invite_token")) return;
  url.searchParams.delete("invite_token");
  window.history.replaceState({}, "", `${url.pathname}${url.search}`);
}

export function LoginPage({ initialApiBase, resetToken, inviteToken, onSignedIn }: LoginPageProps) {
  const initialView: AuthView = resetToken?.trim()
    ? "reset-password"
    : inviteToken?.trim()
      ? "accept-invite"
      : "sign-in";
  const [view, setView] = useState<AuthView>(initialView);
  const [apiBase, setApiBase] = useState(initialApiBase?.trim() || defaultApiBase);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [resetTokenValue, setResetTokenValue] = useState(resetToken?.trim() ?? "");
  const [rememberDevice, setRememberDevice] = useState(() => getRememberDevicePreference());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [invitePreview, setInvitePreview] = useState<OrganizationInvitePreview | null>(null);
  const [invitePreviewLoading, setInvitePreviewLoading] = useState(Boolean(inviteToken?.trim()));

  useEffect(() => {
    const token = inviteToken?.trim();
    if (!token || !apiBase.trim()) {
      setInvitePreviewLoading(false);
      return;
    }
    let cancelled = false;
    setInvitePreviewLoading(true);
    setError(null);
    void (async () => {
      try {
        const preview = await fetchInvitePreview(apiBase.trim(), token);
        if (cancelled) return;
        setInvitePreview(preview);
        setEmail(preview.email);
        if (preview.account_exists) {
          setView("sign-in");
          setInfo(`Sign in to join ${preview.organization_name}.`);
        } else {
          setView("accept-invite");
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setView("sign-in");
        }
      } finally {
        if (!cancelled) setInvitePreviewLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [inviteToken, apiBase]);

  const title = useMemo(() => {
    switch (view) {
      case "create-account":   return "Create account";
      case "verify-2fa":       return "Verify your email";
      case "forgot-password":  return "Forgot password";
      case "reset-password":   return "Reset password";
      case "accept-invite":
        return invitePreview ? `Join ${invitePreview.organization_name}` : "Accept invite";
      default:                 return "Sign in";
    }
  }, [view, invitePreview]);

  function switchView(next: AuthView) {
    setView(next);
    setError(null);
    setInfo(null);
    setPassword("");
    setPasswordConfirm("");
    setOtpCode("");
  }

  async function runAction(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-shell">
      {/* ── Left branding panel ── */}
      <div className="login-brand-panel" aria-hidden="true">
        <div className="login-brand-panel__inner">
          <div className="login-brand-panel__logo">
            <div className="login-brand-panel__icon">SI</div>
            <span className="login-brand-panel__name">Spend Integrity</span>
          </div>
          <h1 className="login-brand-panel__headline">
            Know exactly what you're paying for
          </h1>
          <p className="login-brand-panel__tagline">
            Automated utility bill intelligence for enterprise teams — extraction,
            comparison, and anomaly review at scale.
          </p>
          <ul className="login-features">
            <li>AI-powered bill extraction</li>
            <li>Month-over-month comparison</li>
            <li>Anomaly detection &amp; review</li>
            <li>Multi-site, multi-org support</li>
          </ul>
        </div>
      </div>

      {/* ── Right form panel ── */}
      <div className="login-form-panel">
        <div className="login-form-panel__inner">
          {/* Mobile-only brand mark */}
          <div style={{ marginBottom: "1.5rem", display: "flex", alignItems: "center", gap: "0.6rem" }}>
            <div className="sidebar-brand__icon" style={{ width: "32px", height: "32px", borderRadius: "8px", fontSize: "0.7rem" }}>SI</div>
            <span className="sidebar-brand__name">Spend Integrity</span>
          </div>

          <h2 style={{ margin: "0 0 1.25rem", fontSize: "1.4rem", fontWeight: 800, letterSpacing: "-0.03em" }}>
            {title}
          </h2>

          {/* ── Form fields ── */}
          <section className="card login-card" style={{ marginTop: 0 }}>
            {view !== "verify-2fa" && view !== "reset-password" && view !== "accept-invite" ? (
              <label className="field">
                <span>API base URL</span>
                <input
                  type="text"
                  value={apiBase}
                  onChange={(e) => setApiBase(e.target.value)}
                  placeholder="http://127.0.0.1:8000"
                  autoComplete="off"
                />
              </label>
            ) : null}

            {view === "accept-invite" && invitePreviewLoading ? (
              <p className="hint">Loading invite…</p>
            ) : null}

            {view === "accept-invite" && invitePreview && !invitePreviewLoading ? (
              <p className="hint" style={{ marginTop: 0, marginBottom: "0.75rem" }}>
                You have been invited to <strong>{invitePreview.organization_name}</strong> as{" "}
                <strong>{invitePreview.role}</strong>. Set a password for{" "}
                <strong>{invitePreview.email}</strong> to create your account.
              </p>
            ) : null}

            {view === "sign-in" || view === "create-account" || view === "forgot-password" ? (
              <label className="field">
                <span>Email</span>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="username"
                  placeholder="you@company.com"
                  readOnly={Boolean(inviteToken?.trim() && invitePreview?.email)}
                />
              </label>
            ) : null}

            {view === "sign-in" ||
            view === "create-account" ||
            view === "reset-password" ||
            view === "accept-invite" ? (
              <label className="field">
                <span>
                  {view === "reset-password" || view === "accept-invite" ? "Password" : "Password"}
                </span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={
                    view === "reset-password" || view === "accept-invite"
                      ? "new-password"
                      : "current-password"
                  }
                  placeholder={
                    view === "reset-password" || view === "accept-invite"
                      ? "Choose a password"
                      : "••••••••"
                  }
                />
              </label>
            ) : null}

            {view === "create-account" || view === "reset-password" || view === "accept-invite" ? (
              <label className="field">
                <span>Confirm password</span>
                <input
                  type="password"
                  value={passwordConfirm}
                  onChange={(e) => setPasswordConfirm(e.target.value)}
                  autoComplete="new-password"
                  placeholder="Re-enter password"
                />
              </label>
            ) : null}

            {view === "create-account" || view === "reset-password" || view === "accept-invite" ? (
              <PasswordPolicyHints password={password} />
            ) : null}

            {view === "verify-2fa" ? (
              <>
                <p className="hint" style={{ marginTop: 0, marginBottom: "0.75rem" }}>
                  Enter the verification code sent to <strong>{email}</strong>.
                </p>
                <label className="field">
                  <span>Verification code</span>
                  <input
                    type="text"
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value)}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    placeholder="6-digit code"
                    style={{ letterSpacing: "0.15em", fontSize: "1.1rem" }}
                  />
                </label>
              </>
            ) : null}

            {view === "reset-password" ? (
              <label className="field">
                <span>Reset token</span>
                <input
                  type="text"
                  value={resetTokenValue}
                  onChange={(e) => setResetTokenValue(e.target.value)}
                  autoComplete="off"
                  placeholder="From the reset email link"
                />
              </label>
            ) : null}

            {error ? <p className="error" style={{ marginTop: "0.5rem" }}>{error}</p> : null}
            {info  ? <p style={{ marginTop: "0.5rem", fontSize: "0.9rem", color: "var(--ok)" }}>{info}</p> : null}

            {/* ── Sign in ── */}
            {view === "sign-in" ? (
              <>
                <label className="field field--checkbox" style={{ marginBottom: "1rem" }}>
                  <input
                    type="checkbox"
                    checked={rememberDevice}
                    onChange={(e) => {
                      const checked = e.target.checked;
                      setRememberDevice(checked);
                      setRememberDevicePreference(checked);
                    }}
                  />
                  <span style={{ textTransform: "none", letterSpacing: 0 }}>Remember this device for 30 days</span>
                </label>
                <button
                  type="button"
                  style={{ width: "100%" }}
                  disabled={busy || !apiBase.trim() || !email.trim() || !password}
                  onClick={() =>
                    void runAction(async () => {
                      setRememberDevicePreference(rememberDevice);
                      const res = await loginStart(
                        apiBase.trim(),
                        email.trim(),
                        password,
                        rememberDevice,
                      );
                      if (loginChallengeCompletesSession(res)) {
                        setSession({
                          access_token: res.access_token,
                          token_type: res.token_type ?? "bearer",
                          user: res.user,
                        });
                        onSignedIn(res.user, apiBase.trim());
                        return;
                      }
                      if (!res.challenge_id) {
                        setError("Sign-in requires a verification code but none was issued.");
                        return;
                      }
                      setChallengeId(res.challenge_id);
                      switchView("verify-2fa");
                      setInfo(res.message);
                    })
                  }
                >
                  {busy ? "Signing in…" : "Sign in"}
                </button>
                <p className="auth-links">
                  <button type="button" className="link-btn" onClick={() => switchView("forgot-password")}>
                    Forgot password?
                  </button>
                  <span aria-hidden="true" style={{ margin: "0 0.4rem", color: "var(--text-dim)" }}>·</span>
                  <button type="button" className="link-btn" onClick={() => switchView("create-account")}>
                    Create account
                  </button>
                </p>
                {invitePreview ? (
                  <p className="hint" style={{ marginTop: "0.75rem", textAlign: "center" }}>
                    Invited to <strong>{invitePreview.organization_name}</strong>. Use the email that
                    received the invite.
                  </p>
                ) : (
                  <p className="hint" style={{ marginTop: "0.75rem", textAlign: "center" }}>
                    Production tenants usually join via an email invite from an org admin.
                  </p>
                )}
              </>
            ) : null}

            {/* ── Accept invite (new account) ── */}
            {view === "accept-invite" ? (
              <>
                <label className="field field--checkbox" style={{ marginBottom: "1rem" }}>
                  <input
                    type="checkbox"
                    checked={rememberDevice}
                    onChange={(e) => {
                      const checked = e.target.checked;
                      setRememberDevice(checked);
                      setRememberDevicePreference(checked);
                    }}
                  />
                  <span style={{ textTransform: "none", letterSpacing: 0 }}>Remember this device for 30 days</span>
                </label>
                <button
                  type="button"
                  style={{ width: "100%" }}
                  disabled={
                    invitePreviewLoading ||
                    busy ||
                    !apiBase.trim() ||
                    !inviteToken?.trim() ||
                    !password ||
                    password !== passwordConfirm ||
                    !isPasswordAcceptable(password)
                  }
                  onClick={() =>
                    void runAction(async () => {
                      if (password !== passwordConfirm) {
                        setError("Passwords do not match");
                        return;
                      }
                      if (!isPasswordAcceptable(password)) {
                        setError("Password does not meet the requirements below.");
                        return;
                      }
                      const res = await activateInvite(
                        apiBase.trim(),
                        inviteToken!.trim(),
                        password,
                        rememberDevice,
                      );
                      clearInviteTokenFromUrl();
                      onSignedIn(res.user, apiBase.trim(), {
                        organizationId: res.organization_id,
                      });
                    })
                  }
                >
                  {busy ? "Joining…" : "Set password and join"}
                </button>
              </>
            ) : null}

            {/* ── Create account ── */}
            {view === "create-account" ? (
              <>
                <button
                  type="button"
                  style={{ width: "100%" }}
                  disabled={
                    busy ||
                    !apiBase.trim() ||
                    !email.trim() ||
                    !password ||
                    password !== passwordConfirm ||
                    !isPasswordAcceptable(password)
                  }
                  onClick={() =>
                    void runAction(async () => {
                      if (password !== passwordConfirm) {
                        setError("Passwords do not match");
                        return;
                      }
                      if (!isPasswordAcceptable(password)) {
                        setError("Password does not meet the requirements below.");
                        return;
                      }
                      const res = await register(apiBase.trim(), email.trim(), password);
                      switchView("sign-in");
                      setInfo(res.message);
                    })
                  }
                >
                  {busy ? "Creating…" : "Create account"}
                </button>
                <p className="auth-links">
                  <button type="button" className="link-btn" onClick={() => switchView("sign-in")}>
                    ← Back to sign in
                  </button>
                </p>
              </>
            ) : null}

            {/* ── 2FA verify ── */}
            {view === "verify-2fa" ? (
              <>
                <button
                  type="button"
                  style={{ width: "100%" }}
                  disabled={busy || !challengeId || !otpCode.trim()}
                  onClick={() =>
                    void runAction(async () => {
                      if (!challengeId) {
                        setError("Missing verification session; sign in again.");
                        return;
                      }
                      const res = await loginVerifyOtp(
                        apiBase.trim(),
                        challengeId,
                        otpCode.trim(),
                        rememberDevice,
                      );
                      onSignedIn(res.user, apiBase.trim());
                    })
                  }
                >
                  {busy ? "Verifying…" : "Verify and sign in"}
                </button>
                <p className="auth-links">
                  <button
                    type="button"
                    className="link-btn"
                    onClick={() => {
                      switchView("sign-in");
                      setChallengeId(null);
                    }}
                  >
                    ← Back to sign in
                  </button>
                </p>
              </>
            ) : null}

            {/* ── Forgot password ── */}
            {view === "forgot-password" ? (
              <>
                <button
                  type="button"
                  style={{ width: "100%" }}
                  disabled={busy || !apiBase.trim() || !email.trim()}
                  onClick={() =>
                    void runAction(async () => {
                      const res = await forgotPassword(apiBase.trim(), email.trim());
                      setInfo(res.message);
                    })
                  }
                >
                  {busy ? "Sending…" : "Send reset link"}
                </button>
                <p className="auth-links">
                  <button type="button" className="link-btn" onClick={() => switchView("sign-in")}>
                    ← Back to sign in
                  </button>
                </p>
              </>
            ) : null}

            {/* ── Reset password ── */}
            {view === "reset-password" ? (
              <>
                <button
                  type="button"
                  style={{ width: "100%" }}
                  disabled={
                    busy ||
                    !apiBase.trim() ||
                    !resetTokenValue.trim() ||
                    !password ||
                    password !== passwordConfirm ||
                    !isPasswordAcceptable(password)
                  }
                  onClick={() =>
                    void runAction(async () => {
                      if (password !== passwordConfirm) {
                        setError("Passwords do not match");
                        return;
                      }
                      if (!isPasswordAcceptable(password)) {
                        setError("Password does not meet the requirements below.");
                        return;
                      }
                      const res = await resetPassword(apiBase.trim(), resetTokenValue.trim(), password);
                      setInfo(res.message);
                      if (window.location.search.includes("reset_token")) {
                        const url = new URL(window.location.href);
                        url.searchParams.delete("reset_token");
                        window.history.replaceState({}, "", url.pathname + url.search);
                      }
                      switchView("sign-in");
                    })
                  }
                >
                  {busy ? "Updating…" : "Update password"}
                </button>
                <p className="auth-links">
                  <button type="button" className="link-btn" onClick={() => switchView("sign-in")}>
                    ← Back to sign in
                  </button>
                </p>
              </>
            ) : null}
          </section>
        </div>
      </div>
    </div>
  );
}
