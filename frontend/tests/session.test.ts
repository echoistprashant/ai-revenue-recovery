import { describe, expect, it } from "vitest";

import type { SessionData } from "@/lib/session";
import {
  SESSION_COOKIE,
  cookieSecure,
  decodeSession,
  encodeSession,
  identityOf,
  sessionCookieOptions,
} from "@/lib/session";

const FIXED_NOW = 1_800_000_000_000;

function session(overrides: Partial<SessionData> = {}): SessionData {
  return {
    token: "backend.jwt.value",
    username: "operator1",
    role: "OPERATOR",
    tenantId: "default",
    expiresAt: FIXED_NOW + 60_000,
    ...overrides,
  };
}

function encodeRaw(payload: unknown): string {
  return Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
}

/**
 * `NodeJS.ProcessEnv` declares `NODE_ENV` as required, so a partial fixture needs one
 * deliberate cast. Keeping it here means the individual cases stay readable.
 */
function env(values: Record<string, string>): NodeJS.ProcessEnv {
  return values as unknown as NodeJS.ProcessEnv;
}

describe("codec round trip", () => {
  it("returns exactly what was encoded", () => {
    const original = session();
    expect(decodeSession(encodeSession(original), FIXED_NOW)).toEqual(original);
  });

  it("uses a stable cookie name", () => {
    expect(SESSION_COOKIE).toBe("rr_session");
  });
});

describe("decode fails closed", () => {
  it("treats an absent cookie as not signed in", () => {
    expect(decodeSession(undefined, FIXED_NOW)).toBeNull();
    expect(decodeSession(null, FIXED_NOW)).toBeNull();
    expect(decodeSession("", FIXED_NOW)).toBeNull();
  });

  it("rejects a value that is not base64url JSON", () => {
    expect(decodeSession("not-base64-at-all!!", FIXED_NOW)).toBeNull();
    expect(decodeSession(Buffer.from("{oops", "utf8").toString("base64url"), FIXED_NOW)).toBeNull();
  });

  it("rejects a truncated cookie rather than trusting the prefix", () => {
    const encoded = encodeSession(session());
    expect(decodeSession(encoded.slice(0, encoded.length - 6), FIXED_NOW)).toBeNull();
  });

  it("rejects JSON that is not an object", () => {
    expect(decodeSession(encodeRaw("a string"), FIXED_NOW)).toBeNull();
    expect(decodeSession(encodeRaw(null), FIXED_NOW)).toBeNull();
    expect(decodeSession(encodeRaw([1, 2, 3]), FIXED_NOW)).toBeNull();
  });

  it("requires every field to be present and non-empty", () => {
    expect(decodeSession(encodeRaw({ ...session(), token: "" }), FIXED_NOW)).toBeNull();
    expect(decodeSession(encodeRaw({ ...session(), username: "" }), FIXED_NOW)).toBeNull();
    expect(decodeSession(encodeRaw({ ...session(), tenantId: "" }), FIXED_NOW)).toBeNull();
    const { token: _dropped, ...withoutToken } = session();
    expect(decodeSession(encodeRaw(withoutToken), FIXED_NOW)).toBeNull();
  });

  it("rejects a role this build does not know", () => {
    expect(decodeSession(encodeRaw({ ...session(), role: "SUPERUSER" }), FIXED_NOW)).toBeNull();
    expect(decodeSession(encodeRaw({ ...session(), role: "operator" }), FIXED_NOW)).toBeNull();
    expect(decodeSession(encodeRaw({ ...session(), role: 3 }), FIXED_NOW)).toBeNull();
  });

  it("rejects an expired session, and one expiring exactly now", () => {
    expect(decodeSession(encodeRaw({ ...session(), expiresAt: FIXED_NOW - 1 }), FIXED_NOW)).toBeNull();
    expect(decodeSession(encodeRaw({ ...session(), expiresAt: FIXED_NOW }), FIXED_NOW)).toBeNull();
  });

  it("rejects a non-finite or non-numeric expiry", () => {
    expect(decodeSession(encodeRaw({ ...session(), expiresAt: "later" }), FIXED_NOW)).toBeNull();
    expect(decodeSession(encodeRaw({ ...session(), expiresAt: Number.NaN }), FIXED_NOW)).toBeNull();
    // JSON has no Infinity literal; it serialises to null, which must also be refused.
    expect(decodeSession(encodeRaw({ ...session(), expiresAt: Number.POSITIVE_INFINITY }), FIXED_NOW)).toBeNull();
  });
});

describe("identityOf", () => {
  it("strips the token so a render cannot leak it", () => {
    const identity = identityOf(session());
    expect(identity).not.toHaveProperty("token");
    expect(JSON.stringify(identity)).not.toContain("backend.jwt.value");
    expect(identity.username).toBe("operator1");
  });
});

describe("cookie options", () => {
  it("is httpOnly, strictly same-site, and rooted at /", () => {
    const options = sessionCookieOptions(3600, env({ NODE_ENV: "production" }));
    expect(options.httpOnly).toBe(true);
    expect(options.sameSite).toBe("strict");
    expect(options.path).toBe("/");
    expect(options.maxAge).toBe(3600);
  });

  it("never emits a negative or fractional max-age", () => {
    expect(sessionCookieOptions(-10, env({})).maxAge).toBe(0);
    expect(sessionCookieOptions(12.7, env({})).maxAge).toBe(12);
  });

  it("defaults Secure to on and only drops it when told explicitly", () => {
    expect(cookieSecure(env({ NODE_ENV: "production" }))).toBe(true);
    expect(cookieSecure(env({ FRONTEND_COOKIE_SECURE: "true" }))).toBe(true);
    expect(cookieSecure(env({ FRONTEND_COOKIE_SECURE: "anything-else" }))).toBe(true);
    expect(cookieSecure(env({ FRONTEND_COOKIE_SECURE: "false" }))).toBe(false);
    expect(cookieSecure(env({ FRONTEND_COOKIE_SECURE: "FALSE" }))).toBe(false);
  });

  it("stays insecure-by-omission only outside production", () => {
    expect(cookieSecure(env({ NODE_ENV: "development" }))).toBe(false);
  });
});
