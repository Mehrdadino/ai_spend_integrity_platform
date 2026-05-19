/**
 * Auth gate: sign-in (email 2FA), create account, forgot/reset password.
 */

import { useMemo, useState } from "react";
import { PasswordPolicyHints } from "./components/PasswordPolicyHints";
import { isPasswordAcceptable } from "./lib/passwordPolicy";
import {
  forgotPassword,
  loginChallengeCompletesSession,
  loginStart,
  loginVerifyOtp,
  register,
  resetPassword,
  getRememberDevicePreference,
  setRememberDevicePreference,
  setSession,
  type AuthUser,
} from "./lib/auth";

const defaultApiBase = "http://127.0.0.1:8000";

type AuthView = "sign-in" | "create-account" | "verify-2fa" | "forgot-password" | "reset-password";

type LoginPageProps = {
  initialApiBase?: string;
  resetToken?: string | null;
  onSignedIn: (user: AuthUser, apiBase: string) => void;
};

export function LoginPage({ initialApiBase, resetToken, onSignedIn }: LoginPageProps) {
  const initialView: AuthView = resetToken?.trim() ? "reset-password" : "sign-in";
  const [view, setView] = useState<AuthView>(initialView);
  const [apiBase, setApiBase] = useState(initialApiBase?.trim() || defaultApiBase);
  const [email, setEmail] = useState("admin@dev.local");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [challengeId, setChallengeId] = useState<string | null>(null);
  const [resetTokenValue, setResetTokenValue] = useState(resetToken?.trim() ?? "");
  const [rememberDevice, setRememberDevice] = useState(() => getRememberDevicePreference());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const title = useMemo(() => {
    switch (view) {
      case "create-account":
        return "Create account";
      case "verify-2fa":
        return "Verify your email";
      case "forgot-password":
        return "Forgot password";
      case "reset-password":
        return "Reset password";
      default:
        return "Sign in";
    }
  }, [view]);

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
    <div className="login-page">
      <header className="login-page-header">
        <h1 className="app-title">Spend Integrity</h1>
        <p className="lede">Sign in to review bills and anomalies for your organization.</p>
      </header>
      <section className="card login-card">
        <h2>{title}</h2>

        {view !== "verify-2fa" && view !== "reset-password" ? (
          <label className="field">
            <span>API base URL</span>
            <input
              value={apiBase}
              onChange={(e) => setApiBase(e.target.value)}
              placeholder="http://127.0.0.1:8000"
              autoComplete="off"
            />
          </label>
        ) : null}

        {view === "sign-in" || view === "create-account" || view === "forgot-password" ? (
          <label className="field">
            <span>Email</span>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              type="email"
            />
          </label>
        ) : null}

        {view === "sign-in" || view === "create-account" || view === "reset-password" ? (
          <label className="field">
            <span>{view === "reset-password" ? "New password" : "Password"}</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={view === "reset-password" ? "new-password" : "current-password"}
            />
          </label>
        ) : null}

        {view === "create-account" || view === "reset-password" ? (
          <label className="field">
            <span>Confirm password</span>
            <input
              type="password"
              value={passwordConfirm}
              onChange={(e) => setPasswordConfirm(e.target.value)}
              autoComplete="new-password"
            />
          </label>
        ) : null}

        {view === "create-account" || view === "reset-password" ? (
          <PasswordPolicyHints password={password} />
        ) : null}

        {view === "verify-2fa" ? (
          <>
            <p className="hint">
              Enter the verification code sent to <strong>{email}</strong>.
            </p>
            <label className="field">
              <span>Verification code</span>
              <input
                value={otpCode}
                onChange={(e) => setOtpCode(e.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="6-digit code"
              />
            </label>
          </>
        ) : null}

        {view === "reset-password" ? (
          <label className="field">
            <span>Reset token</span>
            <input
              value={resetTokenValue}
              onChange={(e) => setResetTokenValue(e.target.value)}
              autoComplete="off"
              placeholder="From email link"
            />
          </label>
        ) : null}

        {error ? <p className="error">{error}</p> : null}
        {info ? <p className="success">{info}</p> : null}

        {view === "sign-in" ? (
          <>
            <label className="field field--checkbox">
              <input
                type="checkbox"
                checked={rememberDevice}
                onChange={(e) => {
                  const checked = e.target.checked;
                  setRememberDevice(checked);
                  setRememberDevicePreference(checked);
                }}
              />
              <span>Remember this device for 30 days</span>
            </label>
            <button
              type="button"
              className="primary"
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
              <span aria-hidden="true"> · </span>
              <button type="button" className="link-btn" onClick={() => switchView("create-account")}>
                Create account
              </button>
            </p>
          </>
        ) : null}

        {view === "create-account" ? (
          <>
            <button
              type="button"
              className="primary"
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
                Back to sign in
              </button>
            </p>
          </>
        ) : null}

        {view === "verify-2fa" ? (
          <>
            <button
              type="button"
              className="primary"
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
                Back to sign in
              </button>
            </p>
          </>
        ) : null}

        {view === "forgot-password" ? (
          <>
            <button
              type="button"
              className="primary"
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
                Back to sign in
              </button>
            </p>
          </>
        ) : null}

        {view === "reset-password" ? (
          <>
            <button
              type="button"
              className="primary"
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
                Back to sign in
              </button>
            </p>
          </>
        ) : null}

        {view === "sign-in" ? (
          <p className="hint">
            Dev: <code>admin@dev.local</code> / <code>Dev-Admin-Change1!</code> (from{" "}
            <code>seed_dev_user</code>). Email verification is skipped until{" "}
            <code>SMTP_HOST</code> is set on the API.
          </p>
        ) : null}
      </section>
    </div>
  );
}
