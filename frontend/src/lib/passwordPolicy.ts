/**
 * Password strength rules (mirrors backend ``password_policy.py``).
 */

/** Allowed special characters for new passwords. */
export const ALLOWED_SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?/";

const MIN_LENGTH = 8;
const MAX_LENGTH = 128;

const allowedCharRe = new RegExp(
  `^[A-Za-z0-9${ALLOWED_SPECIAL_CHARS.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}]+$`,
);

/** Short summary shown near password fields. */
export const PASSWORD_REQUIREMENTS_SUMMARY =
  "At least 8 characters, with uppercase, lowercase, a number, and a special character " +
  `(e.g. ! @ # $). Allowed symbols: ${ALLOWED_SPECIAL_CHARS}`;

/** Return issues to show in the UI; empty when acceptable. */
export function getPasswordValidationErrors(password: string): string[] {
  const issues: string[] = [];

  if (password.length < MIN_LENGTH) {
    issues.push(`Use at least ${MIN_LENGTH} characters.`);
  }
  if (password.length > MAX_LENGTH) {
    issues.push(`Use at most ${MAX_LENGTH} characters.`);
  }
  if (password.length > 0 && !allowedCharRe.test(password)) {
    issues.push(
      `Use only letters, numbers, and these symbols: ${ALLOWED_SPECIAL_CHARS.split("").join(" ")}`,
    );
  }
  if (password.length > 0 && !/[a-z]/.test(password)) {
    issues.push("Include at least one lowercase letter.");
  }
  if (password.length > 0 && !/[A-Z]/.test(password)) {
    issues.push("Include at least one uppercase letter.");
  }
  if (password.length > 0 && !/\d/.test(password)) {
    issues.push("Include at least one number.");
  }
  if (password.length > 0 && ![...ALLOWED_SPECIAL_CHARS].some((ch) => password.includes(ch))) {
    issues.push("Include at least one special character (for example ! @ # $ %).");
  }

  return issues;
}

export function isPasswordAcceptable(password: string): boolean {
  return getPasswordValidationErrors(password).length === 0;
}
