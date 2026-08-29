/**
 * Display helpers.
 *
 * Every one of these is total: given `null`, `undefined`, or a non-finite number it
 * returns a placeholder rather than "NaN" or "₹undefined". A dashboard that reports
 * money must not turn a missing score into a confident-looking zero, so an unscored
 * case is rendered as "not scored" and never as 0.0000.
 */

const MISSING = "—";

export function formatCurrency(value: number | null | undefined, currency = "INR"): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return MISSING;
  }
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    // An unknown currency code should not take the page down.
    return `${currency} ${value.toFixed(2)}`;
  }
}

export function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return MISSING;
  }
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

/** A rate already expressed as a fraction (0.42 → "42.0%"). */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return MISSING;
  }
  return `${(value * 100).toFixed(digits)}%`;
}

/** A probability, shown at model precision, or an explicit "not scored". */
export function formatScore(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "not scored";
  }
  return value.toFixed(digits);
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return MISSING;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    // Backend timestamps are ISO strings; if one is not, show it verbatim rather
    // than inventing a date.
    return value;
  }
  return parsed.toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z");
}

/** `RETRY_NOW` → `Retry Now`, for labels only. Raw values stay in tables. */
export function humanizeEnum(value: string | null | undefined): string {
  if (!value) {
    return MISSING;
  }
  return value
    .toLowerCase()
    .split("_")
    .filter(Boolean)
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}

/**
 * Semantic class for an action or state badge. Anything unrecognised is neutral, so a
 * new backend action renders plainly instead of borrowing a misleading colour.
 */
export function toneForAction(action: string | null | undefined): "good" | "warn" | "bad" | "neutral" {
  switch (action) {
    case "RETRY_NOW":
    case "RETRY_LATER":
    case "CHANGE_PAYMENT_METHOD":
    case "RECOVERED":
    case "MANUAL_RECOVERED":
      return "good";
    case "SEND_NOTIFICATION":
    case "ESCALATE_TO_HUMAN":
    case "ESCALATED":
    case "SUPPRESS_RETRY":
    case "PENDING":
      return "warn";
    case "STOP_RECOVERY":
    case "STOPPED":
    case "WRITTEN_OFF":
      return "bad";
    default:
      return "neutral";
  }
}

/** Bar width as a percentage of the largest value in a series. */
export function barWidth(value: number, maximum: number): string {
  if (!Number.isFinite(value) || !Number.isFinite(maximum) || maximum <= 0 || value <= 0) {
    return "0%";
  }
  return `${Math.min(100, (value / maximum) * 100).toFixed(2)}%`;
}
