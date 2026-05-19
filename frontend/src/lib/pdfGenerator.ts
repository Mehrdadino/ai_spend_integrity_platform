/**
 * Minimal pure-TypeScript PDF 1.4 generator for test utility bills.
 *
 * Produces PDFs with an embedded text layer so pypdf (and the LLM extractor)
 * can read them without OCR — making them valid input for the full ingestion
 * + comparison pipeline.
 *
 * No third-party dependencies; uses only standard browser APIs (Blob).
 */

// ── Public types ─────────────────────────────────────────────────────────────

export type UtilityType = "electricity" | "gas" | "water";

export type ScenarioKey =
  | "normal"
  | "mom_spike"
  | "new_fee"
  | "header_mismatch"
  | "penalty_fees"
  | "high_fee_share"
  | "missing_dates"
  | "multi_rule";

export interface BillConfig {
  /** Stable React key. */
  id: string;
  /** Label written into the PDF service address and used in filenames. */
  siteName: string;
  /**
   * Month relative to today: 0 = current month, -1 = last month, etc.
   * Negative values produce past bills; 0 produces a "current month" bill.
   */
  monthOffset: number;
  utility: UtilityType;
  scenario: ScenarioKey;
}

// ── Metadata tables ──────────────────────────────────────────────────────────

export const SCENARIO_LABELS: Record<ScenarioKey, string> = {
  normal:           "Normal bill",
  mom_spike:        "MoM spike +55%",
  new_fee:          "New fee line",
  header_mismatch:  "Header ≠ line sum",
  penalty_fees:     "Penalty / late fees",
  high_fee_share:   "High fee share",
  missing_dates:    "Missing period dates",
  multi_rule:       "Multi-rule (3+ signals)",
};

/** Which comparison rule IDs each scenario is designed to trigger. */
export const SCENARIO_RULES: Record<ScenarioKey, string[]> = {
  normal:           [],
  mom_spike:        ["mom_total_change (critical — 55% over baseline)"],
  new_fee:          ["new_fee_lines"],
  header_mismatch:  ["header_total_mismatch"],
  penalty_fees:     ["penalty_style_fees"],
  high_fee_share:   ["fees_high_share_of_total"],
  missing_dates:    ["missing_period_dates"],
  multi_rule:       ["header_total_mismatch", "penalty_style_fees", "fees_high_share_of_total"],
};

export const SCENARIO_SEVERITY: Record<ScenarioKey, "none" | "info" | "warning" | "critical"> = {
  normal:           "none",
  mom_spike:        "critical",
  new_fee:          "warning",
  header_mismatch:  "warning",
  penalty_fees:     "warning",
  high_fee_share:   "warning",
  missing_dates:    "info",
  multi_rule:       "critical",
};

export const MONTH_OFFSETS: { value: number; label: string }[] = [
  { value: -12, label: "12 months ago" },
  { value: -9,  label: "9 months ago"  },
  { value: -6,  label: "6 months ago"  },
  { value: -5,  label: "5 months ago"  },
  { value: -4,  label: "4 months ago"  },
  { value: -3,  label: "3 months ago"  },
  { value: -2,  label: "2 months ago"  },
  { value: -1,  label: "Last month"    },
  { value:  0,  label: "This month"    },
];

// ── Preset batch definitions ─────────────────────────────────────────────────

export interface PresetDef {
  id: string;
  label: string;
  description: string;
  /** How many bills this preset adds. */
  count: number;
  bills: Omit<BillConfig, "id">[];
}

export const PRESETS: PresetDef[] = [
  {
    id: "mom_pair",
    label: "MoM Spike Pair",
    description:
      "Normal electricity bill (3 mo ago) + spike bill (last month) for the same site. " +
      "Upload both in order to trigger the MoM critical signal.",
    count: 2,
    bills: [
      { siteName: "Site A", monthOffset: -3, utility: "electricity", scenario: "normal"    },
      { siteName: "Site A", monthOffset: -1, utility: "electricity", scenario: "mom_spike" },
    ],
  },
  {
    id: "new_fee_pair",
    label: "New Fee Pair",
    description:
      "Normal gas bill (2 mo ago) + same bill with a late-payment fee added (last month). " +
      "Triggers the new-fee-line signal when uploaded to the same site.",
    count: 2,
    bills: [
      { siteName: "Site B", monthOffset: -2, utility: "gas", scenario: "normal"  },
      { siteName: "Site B", monthOffset: -1, utility: "gas", scenario: "new_fee" },
    ],
  },
  {
    id: "single_issues",
    label: "Single-Bill Issues",
    description:
      "One electricity bill deliberately engineered to fire header mismatch, penalty fees, " +
      "and high fee share — no prior bill needed.",
    count: 1,
    bills: [
      { siteName: "Site C", monthOffset: -1, utility: "electricity", scenario: "multi_rule" },
    ],
  },
  {
    id: "full_suite",
    label: "Full Test Suite (6 bills)",
    description:
      "Two sites with MoM history + one bill with penalty fees + one with missing dates. " +
      "Covers every comparison rule in the rule pack.",
    count: 6,
    bills: [
      { siteName: "Main Street", monthOffset: -4, utility: "electricity", scenario: "normal"        },
      { siteName: "Main Street", monthOffset: -2, utility: "electricity", scenario: "normal"        },
      { siteName: "Main Street", monthOffset:  0, utility: "electricity", scenario: "mom_spike"     },
      { siteName: "Warehouse",   monthOffset: -3, utility: "gas",         scenario: "normal"        },
      { siteName: "Warehouse",   monthOffset: -1, utility: "gas",         scenario: "new_fee"       },
      { siteName: "Downtown",    monthOffset: -1, utility: "water",       scenario: "missing_dates" },
    ],
  },
];

// ── Internal bill data model ──────────────────────────────────────────────────

interface LineItem {
  label: string;
  detail: string;
  amount: number;
}

interface BillData {
  companyName: string;
  tagline: string;
  serviceAddress: string;
  accountNumber: string;
  /** null = missing_dates scenario */
  periodStart: string | null;
  periodEnd: string | null;
  issueDate: string;
  lineItems: LineItem[];
  /** What the PDF "Total Due" header says — may differ from sum of lines. */
  headerTotal: number;
  currency: string;
}

// ── Date helpers ──────────────────────────────────────────────────────────────

const MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function addMonths(date: Date, n: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + n, 1);
}

function fmt(year: number, month: number, day: number): string {
  return `${MON[month - 1]} ${String(day).padStart(2, "0")}, ${year}`;
}

function billDates(monthOffset: number) {
  const now  = new Date();
  const bm   = addMonths(now, monthOffset);
  const yr   = bm.getFullYear();
  const mo   = bm.getMonth() + 1;
  const last = new Date(yr, mo, 0).getDate();
  const im   = addMonths(now, monthOffset + 1);
  return {
    periodStart: fmt(yr, mo, 1),
    periodEnd:   fmt(yr, mo, last),
    issueDate:   fmt(im.getFullYear(), im.getMonth() + 1, 5),
  };
}

function acctNum(siteName: string): string {
  let h = 5821;
  for (let i = 0; i < siteName.length; i++) h = ((h * 31) ^ siteName.charCodeAt(i)) & 0xffff;
  return `${String(h).padStart(4, "0")}-${String(((h * 7) + 1234) & 0xffff).padStart(4, "0")}`;
}

// ── Scenario builders ─────────────────────────────────────────────────────────

const COMPANY: Record<UtilityType, string> = {
  electricity: "Pacific Electric Utilities",
  gas:         "Western Gas and Energy Co.",
  water:       "Metro Water Authority",
};

const TAGLINE: Record<UtilityType, string> = {
  electricity: "Reliable Power for Every Customer Since 1952",
  gas:         "Safe, Affordable Natural Gas for Your Home and Business",
  water:       "Clean Water, Healthy Communities",
};

function sum(items: LineItem[]): number {
  return parseFloat(items.reduce((s, l) => s + l.amount, 0).toFixed(2));
}

function buildBillData(cfg: BillConfig): BillData {
  const dates = billDates(cfg.monthOffset);
  let periodStart: string | null = dates.periodStart;
  let periodEnd:   string | null = dates.periodEnd;
  let items: LineItem[];
  let headerTotal: number;

  switch (cfg.scenario) {
    // ── Normal baseline ──
    case "normal":
      if (cfg.utility === "electricity") {
        items = [
          { label: "Basic service charge", detail: "",                            amount:  12.50 },
          { label: "Energy usage",          detail: "820 kWh @ $0.1200/kWh",     amount:  98.40 },
          { label: "Environmental levy",    detail: "",                            amount:   4.10 },
          { label: "State tax",             detail: "5.5% of usage charges",      amount:   6.32 },
        ];
      } else if (cfg.utility === "gas") {
        items = [
          { label: "Gas distribution charge", detail: "",                         amount:   9.00 },
          { label: "Natural gas supply",       detail: "42 CCF @ $1.2800/CCF",   amount:  53.76 },
          { label: "Delivery charge",          detail: "",                         amount:  14.50 },
          { label: "State tax",                detail: "5.5% of charges",         amount:   4.25 },
          { label: "Regulatory charge",        detail: "",                         amount:   2.10 },
        ];
      } else {
        items = [
          { label: "Water basic service",  detail: "",                            amount:   8.00 },
          { label: "Consumption charge",   detail: "12 CCF @ $4.2500/CCF",       amount:  51.00 },
          { label: "Sewer service",        detail: "",                            amount:   3.50 },
          { label: "Stormwater fee",       detail: "",                            amount:   2.80 },
          { label: "Sales tax",            detail: "5.5%",                        amount:   3.60 },
        ];
      }
      headerTotal = sum(items);
      break;

    // ── Month-over-month spike (~55% over normal) ──
    case "mom_spike":
      if (cfg.utility === "electricity") {
        items = [
          { label: "Basic service charge", detail: "",                            amount:  12.50 },
          { label: "Energy usage",          detail: "1,350 kWh @ $0.1200/kWh",  amount: 162.00 },
          { label: "Environmental levy",    detail: "",                            amount:   4.10 },
          { label: "State tax",             detail: "5.5% of usage charges",      amount:   9.82 },
        ];
      } else if (cfg.utility === "gas") {
        items = [
          { label: "Gas distribution charge", detail: "",                         amount:   9.00 },
          { label: "Natural gas supply",       detail: "68 CCF @ $1.2800/CCF",   amount:  87.04 },
          { label: "Delivery charge",          detail: "",                         amount:  14.50 },
          { label: "State tax",                detail: "5.5% of charges",         amount:   6.08 },
          { label: "Regulatory charge",        detail: "",                         amount:   2.10 },
        ];
      } else {
        items = [
          { label: "Water basic service",  detail: "",                            amount:   8.00 },
          { label: "Consumption charge",   detail: "22 CCF @ $4.2500/CCF",       amount:  93.50 },
          { label: "Sewer service",        detail: "",                            amount:   3.50 },
          { label: "Stormwater fee",       detail: "",                            amount:   2.80 },
          { label: "Sales tax",            detail: "5.5%",                        amount:   5.94 },
        ];
      }
      headerTotal = sum(items);
      break;

    // ── New fee line (late payment appears for first time) ──
    case "new_fee":
      if (cfg.utility === "electricity") {
        items = [
          { label: "Basic service charge", detail: "",                            amount:  12.50 },
          { label: "Energy usage",          detail: "820 kWh @ $0.1200/kWh",     amount:  98.40 },
          { label: "Late payment fee",      detail: "Payment received after due date", amount: 35.00 },
          { label: "Environmental levy",    detail: "",                            amount:   4.10 },
          { label: "State tax",             detail: "5.5% of charges",            amount:   8.25 },
        ];
      } else if (cfg.utility === "gas") {
        items = [
          { label: "Gas distribution charge", detail: "",                         amount:   9.00 },
          { label: "Natural gas supply",       detail: "42 CCF @ $1.2800/CCF",   amount:  53.76 },
          { label: "Late payment fee",         detail: "Past due balance fee",    amount:  35.00 },
          { label: "Delivery charge",          detail: "",                         amount:  14.50 },
          { label: "State tax",                detail: "5.5% of charges",         amount:   6.17 },
          { label: "Regulatory charge",        detail: "",                         amount:   2.10 },
        ];
      } else {
        items = [
          { label: "Water basic service",  detail: "",                            amount:   8.00 },
          { label: "Consumption charge",   detail: "12 CCF @ $4.2500/CCF",       amount:  51.00 },
          { label: "Late payment fee",     detail: "Payment overdue",             amount:  35.00 },
          { label: "Sewer service",        detail: "",                            amount:   3.50 },
          { label: "Stormwater fee",       detail: "",                            amount:   2.80 },
          { label: "Sales tax",            detail: "5.5%",                        amount:   5.52 },
        ];
      }
      headerTotal = sum(items);
      break;

    // ── Header total ≠ sum of line items ──
    case "header_mismatch":
      if (cfg.utility === "electricity") {
        items = [
          { label: "Basic service charge", detail: "",                            amount:  12.50 },
          { label: "Energy usage",          detail: "820 kWh @ $0.1200/kWh",     amount:  98.40 },
          { label: "Environmental levy",    detail: "",                            amount:   4.10 },
          { label: "State tax",             detail: "5.5% of usage charges",      amount:   6.32 },
        ];
      } else if (cfg.utility === "gas") {
        items = [
          { label: "Gas distribution charge", detail: "",                         amount:   9.00 },
          { label: "Natural gas supply",       detail: "42 CCF @ $1.2800/CCF",   amount:  53.76 },
          { label: "Delivery charge",          detail: "",                         amount:  14.50 },
          { label: "State tax",                detail: "5.5% of charges",         amount:   4.25 },
          { label: "Regulatory charge",        detail: "",                         amount:   2.10 },
        ];
      } else {
        items = [
          { label: "Water basic service",  detail: "",                            amount:   8.00 },
          { label: "Consumption charge",   detail: "12 CCF @ $4.2500/CCF",       amount:  51.00 },
          { label: "Sewer service",        detail: "",                            amount:   3.50 },
          { label: "Stormwater fee",       detail: "",                            amount:   2.80 },
          { label: "Sales tax",            detail: "5.5%",                        amount:   3.60 },
        ];
      }
      // Deliberate +$43.50 mismatch (exceeds the 5-cent tolerance in the rule)
      headerTotal = parseFloat((sum(items) + 43.50).toFixed(2));
      break;

    // ── Penalty / late-payment style fees ──
    case "penalty_fees":
      if (cfg.utility === "electricity") {
        items = [
          { label: "Basic service charge",  detail: "",                           amount:  12.50 },
          { label: "Energy usage",           detail: "820 kWh @ $0.1200/kWh",    amount:  98.40 },
          { label: "Late payment penalty",   detail: "Account 30 days past due",  amount:  25.00 },
          { label: "Reconnect fee",          detail: "Service restoration charge", amount: 40.00 },
          { label: "Environmental levy",     detail: "",                           amount:   4.10 },
          { label: "State tax",              detail: "5.5% of charges",           amount:   9.90 },
        ];
      } else if (cfg.utility === "gas") {
        items = [
          { label: "Gas distribution charge", detail: "",                         amount:   9.00 },
          { label: "Natural gas supply",       detail: "42 CCF @ $1.2800/CCF",   amount:  53.76 },
          { label: "Late payment penalty",     detail: "Account past due",        amount:  25.00 },
          { label: "Reconnect fee",            detail: "Service reconnection",    amount:  40.00 },
          { label: "Delivery charge",          detail: "",                         amount:  14.50 },
          { label: "State tax",                detail: "5.5% of charges",         amount:   7.84 },
          { label: "Regulatory charge",        detail: "",                         amount:   2.10 },
        ];
      } else {
        items = [
          { label: "Water basic service",    detail: "",                          amount:   8.00 },
          { label: "Consumption charge",     detail: "12 CCF @ $4.2500/CCF",     amount:  51.00 },
          { label: "Late payment penalty",   detail: "Balance 30+ days overdue", amount:  25.00 },
          { label: "Reconnect fee",          detail: "Service interruption fee",  amount:  40.00 },
          { label: "Sewer service",          detail: "",                          amount:   3.50 },
          { label: "Stormwater fee",         detail: "",                          amount:   2.80 },
          { label: "Sales tax",              detail: "5.5%",                      amount:   7.16 },
        ];
      }
      headerTotal = sum(items);
      break;

    // ── Fees represent >40% of total ──
    case "high_fee_share":
      if (cfg.utility === "electricity") {
        items = [
          { label: "Energy usage",                  detail: "450 kWh @ $0.1200/kWh", amount: 54.00 },
          { label: "Basic service charge",           detail: "",                       amount: 12.50 },
          { label: "Grid modernization fee",         detail: "",                       amount: 14.50 },
          { label: "Renewable energy surcharge",     detail: "",                       amount: 12.00 },
          { label: "Reliability infrastructure fee", detail: "",                       amount: 11.00 },
          { label: "Environmental recovery fee",     detail: "",                       amount:  9.20 },
          { label: "Regulatory compliance fee",      detail: "",                       amount:  7.90 },
          { label: "Administrative processing fee",  detail: "",                       amount:  5.50 },
          { label: "State tax",                      detail: "5.5% of charges",        amount:  7.52 },
        ];
      } else if (cfg.utility === "gas") {
        items = [
          { label: "Natural gas supply",              detail: "20 CCF @ $1.2800/CCF", amount: 25.60 },
          { label: "Gas distribution charge",         detail: "",                      amount:  9.00 },
          { label: "Supplier diversity fee",          detail: "",                      amount: 11.50 },
          { label: "Pipeline maintenance surcharge",  detail: "",                      amount: 10.00 },
          { label: "Safety and infrastructure fee",   detail: "",                      amount:  8.75 },
          { label: "Environmental compliance fee",    detail: "",                      amount:  7.80 },
          { label: "Regulatory recovery surcharge",   detail: "",                      amount:  6.50 },
          { label: "State tax",                       detail: "5.5% of charges",       amount:  4.35 },
        ];
      } else {
        items = [
          { label: "Consumption charge",              detail: "8 CCF @ $4.2500/CCF",  amount: 34.00 },
          { label: "Water basic service",             detail: "",                      amount:  8.00 },
          { label: "Infrastructure improvement fee",  detail: "",                      amount: 11.00 },
          { label: "Stormwater management fee",       detail: "",                      amount:  9.50 },
          { label: "Sewer upgrade surcharge",         detail: "",                      amount:  8.25 },
          { label: "Water quality improvement fee",   detail: "",                      amount:  7.00 },
          { label: "Environmental compliance fee",    detail: "",                      amount:  5.50 },
          { label: "Sales tax",                       detail: "5.5%",                  amount:  4.58 },
        ];
      }
      headerTotal = sum(items);
      break;

    // ── No billing period dates on the bill ──
    case "missing_dates":
      periodStart = null;
      periodEnd   = null;
      if (cfg.utility === "electricity") {
        items = [
          { label: "Basic service charge", detail: "",                            amount:  12.50 },
          { label: "Energy usage",          detail: "820 kWh @ $0.1200/kWh",     amount:  98.40 },
          { label: "Environmental levy",    detail: "",                            amount:   4.10 },
          { label: "State tax",             detail: "5.5% of usage charges",      amount:   6.32 },
        ];
      } else if (cfg.utility === "gas") {
        items = [
          { label: "Gas distribution charge", detail: "",                         amount:   9.00 },
          { label: "Natural gas supply",       detail: "42 CCF @ $1.2800/CCF",   amount:  53.76 },
          { label: "Delivery charge",          detail: "",                         amount:  14.50 },
          { label: "State tax",                detail: "5.5% of charges",         amount:   4.25 },
          { label: "Regulatory charge",        detail: "",                         amount:   2.10 },
        ];
      } else {
        items = [
          { label: "Water basic service",  detail: "",                            amount:   8.00 },
          { label: "Consumption charge",   detail: "12 CCF @ $4.2500/CCF",       amount:  51.00 },
          { label: "Sewer service",        detail: "",                            amount:   3.50 },
          { label: "Stormwater fee",       detail: "",                            amount:   2.80 },
          { label: "Sales tax",            detail: "5.5%",                        amount:   3.60 },
        ];
      }
      headerTotal = sum(items);
      break;

    // ── Multiple rules: header mismatch + penalty fees + high fee share ──
    case "multi_rule":
      if (cfg.utility === "electricity") {
        items = [
          { label: "Energy usage",                  detail: "500 kWh @ $0.1200/kWh",       amount:  60.00 },
          { label: "Basic service charge",           detail: "",                             amount:  12.50 },
          { label: "Late payment penalty",           detail: "Account 60 days past due",    amount:  25.00 },
          { label: "Reconnect fee",                  detail: "Service restoration",          amount:  40.00 },
          { label: "Grid modernization fee",         detail: "",                             amount:  14.50 },
          { label: "Reliability surcharge",          detail: "",                             amount:  11.00 },
          { label: "Environmental recovery fee",     detail: "",                             amount:   9.20 },
          { label: "Regulatory compliance fee",      detail: "",                             amount:   7.90 },
          { label: "State tax",                      detail: "5.5% of charges",              amount:   9.90 },
        ];
      } else if (cfg.utility === "gas") {
        items = [
          { label: "Natural gas supply",              detail: "30 CCF @ $1.2800/CCF",       amount:  38.40 },
          { label: "Gas distribution charge",         detail: "",                            amount:   9.00 },
          { label: "Late payment penalty",            detail: "Account severely past due",   amount:  25.00 },
          { label: "Reconnect fee",                   detail: "Service disconnection fee",   amount:  40.00 },
          { label: "Pipeline maintenance surcharge",  detail: "",                            amount:  10.00 },
          { label: "Safety and infrastructure fee",   detail: "",                            amount:   8.75 },
          { label: "Regulatory recovery surcharge",   detail: "",                            amount:   6.50 },
          { label: "State tax",                       detail: "5.5% of charges",             amount:   7.84 },
        ];
      } else {
        items = [
          { label: "Consumption charge",              detail: "10 CCF @ $4.2500/CCF",       amount:  42.50 },
          { label: "Water basic service",             detail: "",                            amount:   8.00 },
          { label: "Late payment penalty",            detail: "Payment 60+ days past due",  amount:  25.00 },
          { label: "Reconnect fee",                   detail: "Service interruption fee",   amount:  40.00 },
          { label: "Infrastructure improvement fee",  detail: "",                            amount:  11.00 },
          { label: "Stormwater management fee",       detail: "",                            amount:   9.50 },
          { label: "Environmental compliance fee",    detail: "",                            amount:   5.50 },
          { label: "Sales tax",                       detail: "5.5%",                        amount:   7.89 },
        ];
      }
      // Deliberate +$38.50 header mismatch on top of the already-problematic line items
      headerTotal = parseFloat((sum(items) + 38.50).toFixed(2));
      break;

    default:
      items = [];
      headerTotal = 0;
  }

  return {
    companyName:   COMPANY[cfg.utility],
    tagline:       TAGLINE[cfg.utility],
    serviceAddress: `${cfg.siteName}, Portland, OR 97201`,
    accountNumber: acctNum(cfg.siteName),
    periodStart,
    periodEnd,
    issueDate:     dates.issueDate,
    lineItems:     items,
    headerTotal,
    currency:      "USD",
  };
}

// ── PDF binary construction ───────────────────────────────────────────────────

/** Escape text for a PDF literal string (inside parentheses). */
function ps(s: string): string {
  return "(" + s.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)") + ")";
}

/** Keep strings WinAnsi-safe for Type1 Helvetica (pypdf text extraction). */
function asciiSafe(s: string): string {
  return s
    .replace(/\u2014/g, "-")
    .replace(/\u2013/g, "-")
    .replace(/[^\x20-\x7E]/g, "?");
}

/** Build the PDF page content stream for one bill. Returns a pure-ASCII string. */
function buildPageStream(data: BillData): string {
  const cmds: string[] = [];

  // Inner helpers — all push to cmds
  function txt(x: number, y: number, s: string): void {
    // Tm needs the full text matrix: a b c d e f (here: translate to x,y).
    cmds.push(`1 0 0 1 ${x} ${y} Tm`);
    cmds.push(`${ps(asciiSafe(s))} Tj`);
  }
  function font(f: 1 | 2, sz: number, r = 0, g = 0, b = 0): void {
    cmds.push(`${r.toFixed(2)} ${g.toFixed(2)} ${b.toFixed(2)} rg`);
    cmds.push(`/F${f} ${sz} Tf`);
  }
  /**
   * Draw a horizontal rule. Temporarily closes the current BT block, emits
   * path operators, then opens a new BT block.  Callers must be inside a BT.
   */
  function hline(x1: number, y: number, x2: number, gray = 0.80, lw = 0.5): void {
    cmds.push("ET");
    cmds.push(`${gray.toFixed(2)} ${gray.toFixed(2)} ${gray.toFixed(2)} RG`);
    cmds.push(`${lw} w`);
    cmds.push(`${x1} ${y} m ${x2} ${y} l S`);
    cmds.push("0 0 0 RG");
    cmds.push("BT");
  }

  // ── Page content ─────────────────────────────────────────────────────────
  cmds.push("BT");

  // Company name
  font(1, 16, 0.15, 0.35, 0.65);
  txt(50, 750, data.companyName);

  // Tagline
  font(2, 8.5, 0.50, 0.50, 0.50);
  txt(50, 734, data.tagline);

  hline(50, 722, 562);

  // Account info — left column
  font(2, 8, 0.50, 0.50, 0.50);
  txt(50, 708, "Service Address");
  font(2, 9, 0, 0, 0);
  txt(165, 708, data.serviceAddress);

  font(2, 8, 0.50, 0.50, 0.50);
  txt(50, 692, "Account Number");
  font(2, 9, 0, 0, 0);
  txt(165, 692, data.accountNumber);

  // Account info — right column
  font(2, 8, 0.50, 0.50, 0.50);
  txt(360, 708, "Issue Date");
  font(2, 9, 0, 0, 0);
  txt(435, 708, data.issueDate);

  font(2, 8, 0.50, 0.50, 0.50);
  txt(360, 692, "Bill Period");
  if (data.periodStart && data.periodEnd) {
    font(2, 9, 0, 0, 0);
    txt(435, 692, `${data.periodStart} - ${data.periodEnd}`);
  } else {
    font(2, 9, 0.75, 0.30, 0.30);
    txt(435, 692, "Not specified on this bill");
  }

  hline(50, 678, 562);

  // Charges section header
  font(1, 9, 0, 0, 0);
  txt(50, 663, "CHARGES SUMMARY");

  // Column headers
  font(2, 7.5, 0.55, 0.55, 0.55);
  txt(50,  645, "DESCRIPTION");
  txt(308, 645, "DETAIL");
  txt(512, 645, "AMOUNT");

  hline(50, 637, 562, 0.88, 0.3);

  // Line items
  let y = 623;
  for (const item of data.lineItems) {
    font(2, 9, 0, 0, 0);
    txt(50, y, item.label);
    if (item.detail) {
      font(2, 8, 0.50, 0.50, 0.50);
      txt(308, y, item.detail);
    }
    font(2, 9, 0, 0, 0);
    txt(512, y, `$${item.amount.toFixed(2)}`);
    y -= 17;
  }

  // Total separator + total row
  hline(50, y - 4, 562, 0.75, 0.5);
  y -= 22;
  font(1, 11, 0, 0, 0);
  txt(50,  y, "Total Amount Due");
  txt(512, y, `$${data.headerTotal.toFixed(2)}`);

  // Footer
  hline(50, 100, 562, 0.85, 0.3);
  font(2, 7.5, 0.60, 0.60, 0.60);
  txt(50, 84, "Please retain this statement for your records. Questions? Call 1-800-555-0100.");
  txt(50, 70, "Payment due within 30 days of issue date. Mail check to P.O. Box 44100, Portland OR 97204.");
  txt(50, 56, `Currency: ${data.currency}  |  This is a computer-generated statement. No signature required.`);

  cmds.push("ET");
  return cmds.join("\n");
}

/**
 * Assemble a PDF 1.4 document for the given config.
 *
 * Structure: Catalog (1) → Pages (2) → Page (3) → Fonts F1/F2 (4, 5) → Content stream (6).
 * The xref table uses the standard 20-byte-per-entry format with SP+LF EOL.
 */
export function generateBillPdf(cfg: BillConfig): Blob {
  const data   = buildBillData(cfg);
  const stream = buildPageStream(data);
  // Stream is pure ASCII: string length === byte length.
  const streamLen = stream.length;

  // Object bodies (1-indexed; index 0 unused)
  const bodies: string[] = [
    "",
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n" +
      "   /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >>\n" +
      "   /Contents 6 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    `<< /Length ${streamLen} >>\nstream\n${stream}\nendstream`,
  ];

  // Build PDF text and record per-object byte offsets
  let pdf     = "%PDF-1.4\n";
  const offsets: number[] = new Array(7).fill(0);

  for (let i = 1; i <= 6; i++) {
    offsets[i] = pdf.length;
    pdf += `${i} 0 obj\n${bodies[i]}\nendobj\n`;
  }

  // xref — each entry is exactly 20 bytes: "nnnnnnnnnn ggggg n \n"
  const xrefOffset = pdf.length;
  pdf += "xref\n";
  pdf += "0 7\n";
  pdf += "0000000000 65535 f \n";  // free-list head (20 bytes)
  for (let i = 1; i <= 6; i++) {
    pdf += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;

  return new Blob([pdf], { type: "application/pdf" });
}

/** Stable, filesystem-safe filename for a generated bill. */
export function getFilename(cfg: BillConfig): string {
  const site = cfg.siteName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  const mo =
    cfg.monthOffset === 0  ? "current"    :
    cfg.monthOffset === -1 ? "last-month" :
    `${Math.abs(cfg.monthOffset)}mo-ago`;
  return `${site}-${mo}-${cfg.scenario}.pdf`;
}
