/**
 * Which role may reach which module.
 *
 * This is the direct counterpart of `dashboard/access.py` in the Streamlit control
 * centre, deliberately kept as a plain data table with no React or Next imports so
 * the rule can be unit-tested without rendering anything.
 *
 * It is a convenience, not a control. Hiding a link stops a user from stumbling into
 * a page they cannot use; it does not stop anyone from requesting the data. Every
 * backend route re-checks the role on every request, and the API's 403 is the
 * authoritative answer.
 */

export type Role = "VIEWER" | "OPERATOR" | "ADMIN";

/** Ranked roles: a stronger role admits everything a weaker one can do. */
export const ROLE_RANK: Readonly<Record<string, number>> = {
  VIEWER: 1,
  OPERATOR: 2,
  ADMIN: 3,
};

export interface ModuleDefinition {
  /** Route segment under the dashboard shell. */
  readonly href: string;
  readonly label: string;
  readonly icon: string;
  readonly minimum: Role;
  /** One line shown as the page subtitle. */
  readonly summary: string;
}

export const MODULES: readonly ModuleDefinition[] = [
  {
    href: "/overview",
    label: "Executive Overview",
    icon: "📊",
    minimum: "VIEWER",
    summary: "Recovery rate, recovered revenue, and failure mix for your tenant.",
  },
  {
    href: "/operations",
    label: "Payment Operations",
    icon: "💳",
    minimum: "OPERATOR",
    summary: "Ingest a failed payment directly or through a signed gateway webhook.",
  },
  {
    href: "/priority",
    label: "Priority Cases",
    icon: "🎯",
    minimum: "VIEWER",
    summary: "Open cases ranked by recoverable revenue at risk.",
  },
  {
    href: "/review",
    label: "Human Review Queue",
    icon: "🧑‍⚖️",
    minimum: "VIEWER",
    summary: "Escalated cases awaiting a person. Resolving one requires OPERATOR.",
  },
  {
    href: "/decisions",
    label: "Decision Center",
    icon: "🧠",
    minimum: "VIEWER",
    summary: "Ask the deterministic engine what it would do, without writing anything.",
  },
  {
    href: "/optimization",
    label: "Recovery Optimization",
    icon: "🔮",
    minimum: "VIEWER",
    summary: "Retry timing and payment-method recommendations from customer history.",
  },
  {
    href: "/gateway",
    label: "Gateway Health",
    icon: "🏦",
    minimum: "VIEWER",
    summary: "Detect a bank or gateway incident from observed failure rates.",
  },
  {
    href: "/communication",
    label: "Customer Communication",
    icon: "💬",
    minimum: "OPERATOR",
    summary: "Generate customer-facing copy for an action the engine already approved.",
  },
  {
    href: "/analyst",
    label: "AI Revenue Analyst",
    icon: "🤖",
    minimum: "VIEWER",
    summary: "Read-only analytics questions answered from tool output only.",
  },
  {
    href: "/experiments",
    label: "Experiments & What-If",
    icon: "🧪",
    minimum: "VIEWER",
    summary: "Compare a fixed-retry baseline against the intelligent strategy.",
  },
  {
    href: "/monitoring",
    label: "Monitoring & Data Drift",
    icon: "📈",
    minimum: "VIEWER",
    summary: "Request latency, error rate, queue depth, and population stability.",
  },
  {
    href: "/audit",
    label: "Audit & Decision History",
    icon: "📜",
    minimum: "VIEWER",
    summary: "Every decision with its reason, model version, and timestamp.",
  },
  {
    href: "/users",
    label: "User Administration",
    icon: "👥",
    minimum: "ADMIN",
    summary: "Accounts in your tenant. No role here overrides a guardrail.",
  },
];

/**
 * An unrecognised role ranks 0, so a role this build does not know about is shown
 * nothing rather than everything — an older frontend against a newer backend fails
 * closed.
 */
export function allowed(role: string, minimum: Role): boolean {
  return (ROLE_RANK[role] ?? 0) >= ROLE_RANK[minimum]!;
}

export function menuFor(role: string): ModuleDefinition[] {
  return MODULES.filter((module) => allowed(role, module.minimum));
}

/** The module owning a pathname, matching the longest declared prefix. */
export function moduleForPath(pathname: string): ModuleDefinition | undefined {
  const candidates = MODULES.filter(
    (module) => pathname === module.href || pathname.startsWith(`${module.href}/`),
  );
  return candidates.sort((a, b) => b.href.length - a.href.length)[0];
}

/**
 * Whether a role may open a pathname. A path that belongs to no module is not
 * granted by default — the caller decides what to do with an unknown route, and
 * saying "no" here keeps a future page from being reachable before it is classified.
 */
export function canAccessPath(role: string, pathname: string): boolean {
  const module = moduleForPath(pathname);
  if (!module) {
    return false;
  }
  return allowed(role, module.minimum);
}

/** The first module this role can open, used as the post-login landing page. */
export function landingPathFor(role: string): string {
  return menuFor(role)[0]?.href ?? "/login";
}
