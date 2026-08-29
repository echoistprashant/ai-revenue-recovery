/**
 * Paths the browser-facing proxy may forward, as an allowlist.
 *
 * The proxy attaches the caller's own token, so it can never exceed what that user
 * could do holding the token directly — the backend still enforces the role, re-reads
 * the account row, and answers 403 on its own authority. The allowlist exists so the
 * proxy is not a general-purpose tunnel to any current or future backend route: a new
 * endpoint has to be added here on purpose.
 *
 * `/auth/token` and `/webhooks/razorpay` are absent deliberately. Login has its own
 * handler that keeps the issued token server-side, and the webhook is signed on the
 * server so its HMAC secret never reaches the browser.
 *
 * No entry here reaches a payment action directly. `/events` and
 * `/review-queue/{id}/resolve` are the two that can lead to one, and both go through
 * `process_event` / `DecisionEngine` on the backend, where the guardrails sit.
 */

export interface ProxyRule {
  readonly method: "GET" | "POST";
  readonly pattern: RegExp;
}

export const PROXY_ALLOWLIST: readonly ProxyRule[] = [
  { method: "GET", pattern: /^\/auth\/me$/ },
  { method: "GET", pattern: /^\/auth\/users$/ },
  { method: "POST", pattern: /^\/auth\/users$/ },
  { method: "POST", pattern: /^\/auth\/users\/[^/]+\/deactivate$/ },
  { method: "GET", pattern: /^\/metrics$/ },
  { method: "GET", pattern: /^\/operational-metrics$/ },
  { method: "GET", pattern: /^\/priority-cases$/ },
  { method: "GET", pattern: /^\/history$/ },
  { method: "GET", pattern: /^\/audit-log$/ },
  { method: "GET", pattern: /^\/review-queue$/ },
  { method: "POST", pattern: /^\/review-queue\/\d+\/resolve$/ },
  { method: "GET", pattern: /^\/tasks\/stats$/ },
  { method: "POST", pattern: /^\/tasks\/run-due$/ },
  { method: "POST", pattern: /^\/events$/ },
  { method: "POST", pattern: /^\/recommendations$/ },
  { method: "POST", pattern: /^\/decisions$/ },
  { method: "POST", pattern: /^\/gateway-health$/ },
  { method: "POST", pattern: /^\/communication$/ },
  { method: "POST", pattern: /^\/analyst$/ },
  { method: "POST", pattern: /^\/experiments$/ },
  { method: "POST", pattern: /^\/drift$/ },
];

export function isProxyable(method: string, path: string): boolean {
  const normalized = `/${path.replace(/^\/+/, "")}`;
  // A traversal segment can never make a path legal, but rejecting it up front means
  // no downstream URL builder has to be trusted to normalize it the same way.
  if (normalized.includes("..")) {
    return false;
  }
  return PROXY_ALLOWLIST.some((rule) => rule.method === method && rule.pattern.test(normalized));
}
