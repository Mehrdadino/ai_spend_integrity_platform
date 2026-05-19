/**
 * Signed-in account settings: change email and change password.
 */

import { useEffect, useState } from "react";
import { PasswordPolicyHints } from "./components/PasswordPolicyHints";
import { changeEmail, changePassword, type AuthUser } from "./lib/auth";
import { isPasswordAcceptable } from "./lib/passwordPolicy";

type AccountPageProps = {
  apiBase: string;
  user: AuthUser;
  onUserUpdated: (user: AuthUser) => void;
};

export function AccountPage({ apiBase, user, onUserUpdated }: AccountPageProps) {
  const [currentPasswordEmail, setCurrentPasswordEmail] = useState("");
  const [newEmail, setNewEmail] = useState(user.email);
  const [emailBusy, setEmailBusy] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [emailInfo, setEmailInfo] = useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordConfirm, setNewPasswordConfirm] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordInfo, setPasswordInfo] = useState<string | null>(null);

  useEffect(() => {
    setNewEmail(user.email);
  }, [user.email]);

  return (
    <div className="account-page">
      <section className="card account-card">
        <h2>Change email</h2>
        <p className="card-subtitle">Your login identifier. You will stay signed in with a refreshed session.</p>
        <label className="field">
          <span>New email</span>
          <input
            type="email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            autoComplete="email"
          />
        </label>
        <label className="field">
          <span>Current password</span>
          <input
            type="password"
            value={currentPasswordEmail}
            onChange={(e) => setCurrentPasswordEmail(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        {emailError ? <p className="error">{emailError}</p> : null}
        {emailInfo ? <p className="success">{emailInfo}</p> : null}
        <button
          type="button"
          className="primary"
          disabled={emailBusy || !newEmail.trim() || !currentPasswordEmail}
          onClick={() => {
            void (async () => {
              setEmailBusy(true);
              setEmailError(null);
              setEmailInfo(null);
              try {
                const res = await changeEmail(
                  apiBase,
                  newEmail.trim(),
                  currentPasswordEmail,
                );
                onUserUpdated(res.user);
                setEmailInfo("Email updated.");
                setCurrentPasswordEmail("");
              } catch (e) {
                setEmailError(e instanceof Error ? e.message : String(e));
              } finally {
                setEmailBusy(false);
              }
            })();
          }}
        >
          {emailBusy ? "Saving…" : "Update email"}
        </button>
      </section>

      <section className="card account-card">
        <h2>Change password</h2>
        <p className="card-subtitle">You stay signed in on this device after updating.</p>
        <label className="field">
          <span>Current password</span>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        <label className="field">
          <span>New password</span>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            autoComplete="new-password"
          />
        </label>
        <label className="field">
          <span>Confirm new password</span>
          <input
            type="password"
            value={newPasswordConfirm}
            onChange={(e) => setNewPasswordConfirm(e.target.value)}
            autoComplete="new-password"
          />
        </label>
        <PasswordPolicyHints password={newPassword} />
        {passwordError ? <p className="error">{passwordError}</p> : null}
        {passwordInfo ? <p className="success">{passwordInfo}</p> : null}
        <button
          type="button"
          className="primary"
          disabled={
            passwordBusy ||
            !currentPassword ||
            !newPassword ||
            newPassword !== newPasswordConfirm ||
            !isPasswordAcceptable(newPassword)
          }
          onClick={() => {
            void (async () => {
              if (newPassword !== newPasswordConfirm) {
                setPasswordError("Passwords do not match");
                return;
              }
              if (!isPasswordAcceptable(newPassword)) {
                setPasswordError("New password does not meet the requirements below.");
                return;
              }
              setPasswordBusy(true);
              setPasswordError(null);
              setPasswordInfo(null);
              try {
                const res = await changePassword(apiBase, currentPassword, newPassword);
                setPasswordInfo(res.message);
                setCurrentPassword("");
                setNewPassword("");
                setNewPasswordConfirm("");
              } catch (e) {
                setPasswordError(e instanceof Error ? e.message : String(e));
              } finally {
                setPasswordBusy(false);
              }
            })();
          }}
        >
          {passwordBusy ? "Saving…" : "Update password"}
        </button>
      </section>
    </div>
  );
}
