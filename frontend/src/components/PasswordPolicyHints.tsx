/**
 * Requirements summary and live validation messages for new-password fields.
 */

import {
  getPasswordValidationErrors,
  PASSWORD_REQUIREMENTS_SUMMARY,
} from "../lib/passwordPolicy";

type PasswordPolicyHintsProps = {
  password: string;
  /** When false, only show issues after the user has typed something. */
  showRequirements?: boolean;
};

export function PasswordPolicyHints({
  password,
  showRequirements = true,
}: PasswordPolicyHintsProps) {
  const issues = password.length > 0 ? getPasswordValidationErrors(password) : [];

  return (
    <div className="password-policy">
      {showRequirements ? (
        <p className="hint password-policy__summary">{PASSWORD_REQUIREMENTS_SUMMARY}</p>
      ) : null}
      {issues.length > 0 ? (
        <ul className="password-policy__issues" aria-live="polite">
          {issues.map((msg) => (
            <li key={msg}>{msg}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
