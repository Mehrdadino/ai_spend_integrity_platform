/**
 * Display formatting for currency amounts in the UI (two fractional digits).
 */

/** Format a numeric amount for display; returns em-dash when missing or invalid. */
export function formatMoney(
  value: string | number | null | undefined,
  currency?: string,
): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const n = typeof value === "number" ? value : Number.parseFloat(String(value));
  if (Number.isNaN(n)) {
    return String(value);
  }
  const amount = n.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const code = currency?.trim();
  return code ? `${amount} ${code}` : amount;
}
