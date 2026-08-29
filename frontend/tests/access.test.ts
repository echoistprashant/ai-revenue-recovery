import { describe, expect, it } from "vitest";

import {
  MODULES,
  ROLE_RANK,
  allowed,
  canAccessPath,
  landingPathFor,
  menuFor,
  moduleForPath,
} from "@/lib/access";

describe("role ranking", () => {
  it("ranks VIEWER below OPERATOR below ADMIN", () => {
    expect(ROLE_RANK.VIEWER).toBeLessThan(ROLE_RANK.OPERATOR!);
    expect(ROLE_RANK.OPERATOR).toBeLessThan(ROLE_RANK.ADMIN!);
  });

  it("admits everything a weaker role can do", () => {
    expect(allowed("ADMIN", "VIEWER")).toBe(true);
    expect(allowed("ADMIN", "OPERATOR")).toBe(true);
    expect(allowed("OPERATOR", "VIEWER")).toBe(true);
  });

  it("refuses to promote a weaker role", () => {
    expect(allowed("VIEWER", "OPERATOR")).toBe(false);
    expect(allowed("OPERATOR", "ADMIN")).toBe(false);
  });

  it("fails closed on a role this build does not know", () => {
    // An older frontend against a newer backend must show nothing, not everything.
    expect(allowed("SUPERUSER", "VIEWER")).toBe(false);
    expect(allowed("", "VIEWER")).toBe(false);
    expect(allowed("viewer", "VIEWER")).toBe(false);
  });
});

describe("menuFor", () => {
  it("gives a VIEWER only VIEWER modules", () => {
    const menu = menuFor("VIEWER");
    expect(menu.every((module) => module.minimum === "VIEWER")).toBe(true);
    expect(menu.map((module) => module.href)).not.toContain("/users");
    expect(menu.map((module) => module.href)).not.toContain("/operations");
  });

  it("gives an ADMIN every module", () => {
    expect(menuFor("ADMIN")).toHaveLength(MODULES.length);
  });

  it("gives an unknown role an empty menu", () => {
    expect(menuFor("NOBODY")).toHaveLength(0);
  });

  it("keeps user administration behind ADMIN", () => {
    expect(menuFor("OPERATOR").map((module) => module.href)).not.toContain("/users");
  });
});

describe("moduleForPath", () => {
  it("matches an exact route", () => {
    expect(moduleForPath("/overview")?.label).toBe("Executive Overview");
  });

  it("matches a nested route through its prefix", () => {
    expect(moduleForPath("/audit/42")?.href).toBe("/audit");
  });

  it("returns nothing for an unclassified route", () => {
    expect(moduleForPath("/not-a-module")).toBeUndefined();
  });
});

describe("canAccessPath", () => {
  it("enforces the module minimum", () => {
    expect(canAccessPath("VIEWER", "/overview")).toBe(true);
    expect(canAccessPath("VIEWER", "/operations")).toBe(false);
    expect(canAccessPath("OPERATOR", "/operations")).toBe(true);
    expect(canAccessPath("ADMIN", "/users")).toBe(true);
    expect(canAccessPath("OPERATOR", "/users")).toBe(false);
  });

  it("denies a route that belongs to no module", () => {
    // A future page must not be reachable before it is classified.
    expect(canAccessPath("ADMIN", "/unreleased")).toBe(false);
  });
});

describe("landingPathFor", () => {
  it("lands every known role on a page it can actually open", () => {
    for (const role of ["VIEWER", "OPERATOR", "ADMIN"] as const) {
      expect(canAccessPath(role, landingPathFor(role))).toBe(true);
    }
  });

  it("sends an unknown role to the login page", () => {
    expect(landingPathFor("NOBODY")).toBe("/login");
  });
});
