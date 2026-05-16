/**
 * First screen: API URL + email/password (no organization UUID).
 */

import { useState } from "react";
import { login, type AuthUser } from "./lib/auth";

const defaultApiBase = "http://127.0.0.1:8000";

type LoginPageProps = {
  initialApiBase?: string;
  onSignedIn: (user: AuthUser, apiBase: string) => void;
};

export function LoginPage({ initialApiBase, onSignedIn }: LoginPageProps) {
  const [apiBase, setApiBase] = useState(initialApiBase?.trim() || defaultApiBase);
  const [email, setEmail] = useState("admin@dev.local");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="login-page">
      <header className="login-page-header">
        <h1 className="app-title">Spend Integrity</h1>
        <p className="lede">Sign in to review bills and anomalies for your organization.</p>
      </header>
      <section className="card login-card">
        <h2>Sign in</h2>
        <label className="field">
          <span>API base URL</span>
          <input
            value={apiBase}
            onChange={(e) => setApiBase(e.target.value)}
            placeholder="http://127.0.0.1:8000"
            autoComplete="off"
          />
        </label>
        <label className="field">
          <span>Email</span>
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
          />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error ? <p className="error">{error}</p> : null}
        <button
          type="button"
          className="primary"
          disabled={busy || !apiBase.trim() || !email.trim() || !password}
          onClick={() => {
            void (async () => {
              setBusy(true);
              setError(null);
              try {
                const res = await login(apiBase.trim(), email.trim(), password);
                onSignedIn(res.user, apiBase.trim());
              } catch (e) {
                setError(e instanceof Error ? e.message : String(e));
              } finally {
                setBusy(false);
              }
            })();
          }}
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="hint">
          Dev: run <code>python -m app.scripts.seed_dev_user</code> after migrations (default{" "}
          <code>admin@dev.local</code> / <code>dev-admin-change-me</code>).
        </p>
      </section>
    </div>
  );
}
