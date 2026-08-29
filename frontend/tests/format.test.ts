import { describe, expect, it } from "vitest";

import {
  barWidth,
  formatCurrency,
  formatNumber,
  formatPercent,
  formatScore,
  formatTimestamp,
  humanizeEnum,
  toneForAction,
} from "@/lib/format";

const MISSING = "—";

describe("formatters never invent a number", () => {
  it("renders a missing amount as a placeholder, not zero", () => {
    expect(formatCurrency(null)).toBe(MISSING);
    expect(formatCurrency(undefined)).toBe(MISSING);
    expect(formatCurrency(Number.NaN)).toBe(MISSING);
    expect(formatCurrency(Number.POSITIVE_INFINITY)).toBe(MISSING);
  });

  it("renders a missing count as a placeholder", () => {
    expect(formatNumber(null)).toBe(MISSING);
    expect(formatNumber(Number.NaN)).toBe(MISSING);
  });

  it("renders a missing rate as a placeholder", () => {
    expect(formatPercent(null)).toBe(MISSING);
    expect(formatPercent(undefined)).toBe(MISSING);
  });

  it("says a case is not scored rather than showing 0.0000", () => {
    expect(formatScore(null)).toBe("not scored");
    expect(formatScore(undefined)).toBe("not scored");
    expect(formatScore(Number.NaN)).toBe("not scored");
  });

  it("still shows a genuine zero score as zero", () => {
    // A scored-at-zero case and an unscored case must not look the same.
    expect(formatScore(0)).toBe("0.0000");
  });

  it("keeps a real zero amount distinct from a missing one", () => {
    expect(formatCurrency(0)).not.toBe(MISSING);
    expect(formatNumber(0)).toBe("0");
  });
});

describe("value rendering", () => {
  it("formats a rate already expressed as a fraction", () => {
    expect(formatPercent(0.42)).toBe("42.0%");
    expect(formatPercent(1)).toBe("100.0%");
    expect(formatPercent(0.4237, 2)).toBe("42.37%");
  });

  it("formats a score at model precision", () => {
    expect(formatScore(0.87342)).toBe("0.8734");
    expect(formatScore(0.5, 2)).toBe("0.50");
  });

  it("includes a currency symbol, and uses the code itself when it is unfamiliar", () => {
    expect(formatCurrency(2499)).toContain("2,499");
    // A well-formed but unknown ISO code does not throw: Intl uses it as the symbol,
    // separated by a non-breaking space rather than a plain one.
    expect(formatCurrency(1000, "ZZZ")).toBe("ZZZ 1,000.00");
  });

  it("falls back instead of throwing on a malformed currency code", () => {
    // Intl only rejects codes that are not three letters, and a bad code must not
    // take the page down.
    expect(formatCurrency(1000, "BADCODE")).toBe("BADCODE 1000.00");
    expect(formatCurrency(1000, "")).toBe(" 1000.00");
  });
});

describe("formatTimestamp", () => {
  it("renders an ISO timestamp compactly in UTC", () => {
    expect(formatTimestamp("2026-08-30T11:22:33.456Z")).toBe("2026-08-30 11:22:33Z");
  });

  it("shows an unparseable value verbatim rather than inventing a date", () => {
    expect(formatTimestamp("whenever")).toBe("whenever");
  });

  it("renders an absent timestamp as a placeholder", () => {
    expect(formatTimestamp(null)).toBe(MISSING);
    expect(formatTimestamp("")).toBe(MISSING);
  });
});

describe("humanizeEnum", () => {
  it("title-cases an underscored enum for labels", () => {
    expect(humanizeEnum("RETRY_NOW")).toBe("Retry Now");
    expect(humanizeEnum("CHANGE_PAYMENT_METHOD")).toBe("Change Payment Method");
  });

  it("handles an absent value and stray underscores", () => {
    expect(humanizeEnum(null)).toBe(MISSING);
    expect(humanizeEnum("__PENDING__")).toBe("Pending");
  });
});

describe("toneForAction", () => {
  it("marks a stopped or written-off outcome as bad", () => {
    expect(toneForAction("STOP_RECOVERY")).toBe("bad");
    expect(toneForAction("WRITTEN_OFF")).toBe("bad");
  });

  it("marks a withheld or escalated action as a warning, not a failure", () => {
    // Refusing to act on a fraud decline is the system working, not an error.
    expect(toneForAction("SUPPRESS_RETRY")).toBe("warn");
    expect(toneForAction("ESCALATE_TO_HUMAN")).toBe("warn");
    expect(toneForAction("PENDING")).toBe("warn");
  });

  it("marks a recovery or an active retry as good", () => {
    expect(toneForAction("RETRY_NOW")).toBe("good");
    expect(toneForAction("RECOVERED")).toBe("good");
    expect(toneForAction("MANUAL_RECOVERED")).toBe("good");
  });

  it("gives an unrecognised action a neutral tone", () => {
    // A new backend action must render plainly rather than borrow a misleading colour.
    expect(toneForAction("SOME_NEW_ACTION")).toBe("neutral");
    expect(toneForAction(null)).toBe("neutral");
    expect(toneForAction("")).toBe("neutral");
  });
});

describe("barWidth", () => {
  it("scales a value against the series maximum", () => {
    expect(barWidth(50, 200)).toBe("25.00%");
    expect(barWidth(200, 200)).toBe("100.00%");
  });

  it("clamps rather than overflowing its container", () => {
    expect(barWidth(400, 200)).toBe("100.00%");
  });

  it("collapses to zero for a degenerate series", () => {
    expect(barWidth(10, 0)).toBe("0%");
    expect(barWidth(-5, 200)).toBe("0%");
    expect(barWidth(Number.NaN, 200)).toBe("0%");
    expect(barWidth(10, Number.NaN)).toBe("0%");
  });
});
