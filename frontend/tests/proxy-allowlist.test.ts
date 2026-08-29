import { describe, expect, it } from "vitest";

import { PROXY_ALLOWLIST, isProxyable } from "@/lib/proxy-allowlist";

describe("the proxy is an allowlist, not a tunnel", () => {
  it("forwards the routes the UI actually needs", () => {
    expect(isProxyable("GET", "/metrics")).toBe(true);
    expect(isProxyable("GET", "/priority-cases")).toBe(true);
    expect(isProxyable("GET", "/review-queue")).toBe(true);
    expect(isProxyable("POST", "/events")).toBe(true);
    expect(isProxyable("POST", "/decisions")).toBe(true);
    expect(isProxyable("POST", "/tasks/run-due")).toBe(true);
  });

  it("refuses a backend route nobody put on the list", () => {
    expect(isProxyable("GET", "/health")).toBe(false);
    expect(isProxyable("GET", "/openapi.json")).toBe(false);
    expect(isProxyable("POST", "/some/future/route")).toBe(false);
  });
});

describe("the two deliberate exclusions", () => {
  it("never forwards /auth/token", () => {
    // Login has its own handler so the issued token stays server-side.
    expect(isProxyable("POST", "/auth/token")).toBe(false);
    expect(isProxyable("GET", "/auth/token")).toBe(false);
  });

  it("never forwards /webhooks/razorpay", () => {
    // The HMAC secret must not reach the browser, so signing stays in a route handler.
    expect(isProxyable("POST", "/webhooks/razorpay")).toBe(false);
    expect(isProxyable("GET", "/webhooks/razorpay")).toBe(false);
  });

  it("has no allowlist entry mentioning either path", () => {
    for (const rule of PROXY_ALLOWLIST) {
      expect(rule.pattern.test("/auth/token")).toBe(false);
      expect(rule.pattern.test("/webhooks/razorpay")).toBe(false);
    }
  });
});

describe("method and shape are both part of the rule", () => {
  it("does not let a read route be written to", () => {
    expect(isProxyable("POST", "/metrics")).toBe(false);
    expect(isProxyable("POST", "/history")).toBe(false);
  });

  it("does not let a write route be read", () => {
    expect(isProxyable("GET", "/events")).toBe(false);
    expect(isProxyable("GET", "/decisions")).toBe(false);
  });

  it("rejects a method the allowlist does not model at all", () => {
    expect(isProxyable("DELETE", "/events")).toBe(false);
    expect(isProxyable("PUT", "/events")).toBe(false);
    expect(isProxyable("get", "/metrics")).toBe(false);
  });

  it("requires a numeric event id on resolve", () => {
    expect(isProxyable("POST", "/review-queue/12/resolve")).toBe(true);
    expect(isProxyable("POST", "/review-queue/abc/resolve")).toBe(false);
    expect(isProxyable("POST", "/review-queue/12/approve")).toBe(false);
  });

  it("allows exactly one username segment on deactivate", () => {
    expect(isProxyable("POST", "/auth/users/alice/deactivate")).toBe(true);
    expect(isProxyable("POST", "/auth/users/alice/bob/deactivate")).toBe(false);
    expect(isProxyable("POST", "/auth/users/alice/promote")).toBe(false);
  });
});

describe("path normalisation cannot be used to escape the list", () => {
  it("rejects any traversal segment", () => {
    expect(isProxyable("POST", "/events/../auth/token")).toBe(false);
    expect(isProxyable("GET", "/metrics/..")).toBe(false);
    expect(isProxyable("GET", "/../metrics")).toBe(false);
  });

  it("treats a missing or doubled leading slash the same way", () => {
    expect(isProxyable("GET", "metrics")).toBe(true);
    expect(isProxyable("GET", "//metrics")).toBe(true);
    expect(isProxyable("POST", "auth/token")).toBe(false);
    expect(isProxyable("POST", "//auth/token")).toBe(false);
  });

  it("does not admit a longer path that merely starts with an allowed one", () => {
    expect(isProxyable("GET", "/metrics/all")).toBe(false);
    expect(isProxyable("POST", "/eventsx")).toBe(false);
  });
});
