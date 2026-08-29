import { describe, expect, it } from "vitest";

import { RECOVERY_ACTIONS, WITHHELD_ACTIONS, isWithheld, type RecoveryAction } from "@/lib/types";

/**
 * These mirror the backend enum in `src/revenue_recovery/models.py`. A drift here shows
 * up as a UI that silently renders an unknown action, so the list is asserted directly.
 */
describe("recovery actions mirror the backend", () => {
  it("declares exactly the seven backend actions", () => {
    expect([...RECOVERY_ACTIONS].sort()).toEqual(
      [
        "CHANGE_PAYMENT_METHOD",
        "ESCALATE_TO_HUMAN",
        "RETRY_LATER",
        "RETRY_NOW",
        "SEND_NOTIFICATION",
        "STOP_RECOVERY",
        "SUPPRESS_RETRY",
      ].sort(),
    );
  });

  it("has no NO_ACTION value, because the backend has none", () => {
    // "Nothing happened" is expressed by the forced action itself, not a sentinel.
    expect(RECOVERY_ACTIONS).not.toContain("NO_ACTION" as RecoveryAction);
  });
});

describe("isWithheld", () => {
  it("treats a guardrail-forced outcome as withheld", () => {
    expect(isWithheld("SUPPRESS_RETRY")).toBe(true);
    expect(isWithheld("STOP_RECOVERY")).toBe(true);
    expect(isWithheld("ESCALATE_TO_HUMAN")).toBe(true);
  });

  it("does not call an attempted action withheld", () => {
    expect(isWithheld("RETRY_NOW")).toBe(false);
    expect(isWithheld("RETRY_LATER")).toBe(false);
    expect(isWithheld("CHANGE_PAYMENT_METHOD")).toBe(false);
    // A notification is a real outbound action, not a refusal.
    expect(isWithheld("SEND_NOTIFICATION")).toBe(false);
  });

  it("classifies every declared action one way or the other", () => {
    for (const action of RECOVERY_ACTIONS) {
      expect(typeof isWithheld(action)).toBe("boolean");
    }
    expect(WITHHELD_ACTIONS.every((action) => RECOVERY_ACTIONS.includes(action))).toBe(true);
  });
});
