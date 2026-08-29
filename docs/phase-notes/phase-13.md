# Phase 13 — Production Next.js Control Centre

## Objective

Replace the Streamlit control centre with a production frontend at full feature parity,
without moving any decision, guardrail, or credential into the browser. Streamlit stays
in the repository and keeps working; this phase adds the surface intended for real
operators.

## Why this was needed

Streamlit holds its session in server memory and re-runs the whole script on every
interaction. That is fine for a demonstration and wrong for an operations console: there
is no route-level access control, no way to link a colleague to one case, and the bearer
token lives in a process global. The parity requirement was deliberate — a second UI
that quietly drops the review queue or the withheld-action rendering would make the two
disagree about what the system did.

## Implemented

### Session as a backend-for-frontend (`app/api/auth/*`, `lib/session.ts`)

Sign-in posts to this app's own route handler, which calls `/auth/token` server-side and
writes the returned bearer token into an httpOnly, `SameSite=Strict`, `Secure` cookie.
Browser JavaScript never holds a credential that authorises a payment action; an XSS in
a dependency can at most make requests the operator could already make, and a cross-site
form post carries no session at all.

`lib/session.ts` holds the codec and is free of Next imports, so its fail-closed
behaviour is unit-testable: a tampered, truncated, expired, or unknown-role cookie
decodes to `null` — "not signed in" rather than a partially trusted identity. There is
no signature on the cookie because there is nothing to forge in it. The only field the
backend trusts is the token, which is itself signed and re-checked on every request;
editing `role` in the cookie changes which links get drawn and nothing else.

`Secure` defaults on and is dropped only by setting `FRONTEND_COOKIE_SECURE=false`,
which local HTTP development needs and production must not set.

### Allowlisted proxy (`app/api/backend/[...path]/route.ts`, `lib/proxy-allowlist.ts`)

The browser reaches the API only through 21 explicit `(method, pattern)` rules. The
proxy attaches the caller's own token, so it can never exceed what that operator could
do holding the token directly — the backend still enforces the role, re-reads the
account row, and answers 403 on its own authority. The allowlist exists so the proxy is
not a general-purpose tunnel: a new endpoint has to be added on purpose.

`/auth/token` and `/webhooks/razorpay` are absent deliberately, and a test asserts no
rule matches either. Login keeps its issued token server-side; the webhook is signed in
a route handler so its HMAC secret never reaches the browser. Any path containing `..`
is refused before a URL builder sees it.

Two allowlisted routes can lead to a payment action — `POST /events` and
`POST /review-queue/{id}/resolve` — and both enter the backend through `process_event` /
`DecisionEngine`, where the guardrails already sit. The frontend adds no new path to an
action and no field that could skip one.

### No middleware

`app/(dashboard)/layout.tsx` is the single session gate. Putting the same rule in
`middleware.ts` would duplicate it into the Edge runtime, where the two copies could
drift; one server-side gate that every dashboard page renders under cannot.

### Thirteen module pages at parity

`overview`, `operations`, `priority`, `review`, `decisions`, `optimization`, `gateway`,
`communication`, `analyst`, `experiments`, `monitoring`, `audit`, `users`. Presets,
captions, synthetic generator formulas, and safety callouts were read out of
`dashboard/app.py` rather than reinvented, so the two UIs describe the same system.

Menu and route access come from `lib/access.ts`, the counterpart of
`dashboard/access.py`, kept as a plain data table with no React imports so the rule can
be tested without rendering. An unrecognised role ranks 0 and sees nothing, so an older
frontend against a newer backend fails closed. Hiding a link is a convenience, not a
control: every backend route re-checks the role and the API's 403 is authoritative.

Limits and drill-downs live in `searchParams`, so most pages ship no client JavaScript
and a case link is shareable. Charts are CSS bars scaled to the series maximum — no
charting dependency.

### Safety rendering

A withheld action is shown as a withheld action. `lib/types.ts` gained
`WITHHELD_ACTIONS` / `isWithheld()` covering `SUPPRESS_RETRY`, `ESCALATE_TO_HUMAN`, and
`STOP_RECOVERY`; those render amber, not red, because refusing to retry a fraud decline
or a capped attempt is the system working. A duplicate says "first decision replayed".
The experiment page prints the 95% interval before the verdict. Drift is labelled a
monitoring signal that changes no financial decision. The user page states plainly that
`ADMIN` gains no guardrail override.

Every formatter in `lib/format.ts` is total: a missing value renders as `—`, and an
unscored case as "not scored" rather than `0.0000`, so a dashboard that reports money
never turns absent data into a confident zero.

### Packaging and CI

`frontend/Dockerfile` builds in three stages on `node:22-alpine` against Next's
`standalone` output and runs as a non-root user. The build stage runs
`npm run typecheck && npm run test && npm run build`, so an image that cannot pass its
own checks is never produced. `docker-compose.yml` gained a `frontend` service on port
3000 pointing at `http://api:8000`. `.github/workflows/test.yml` gained a `frontend` job
mirroring the backend job's shape: checkout, Node 22 with npm cache keyed on
`frontend/package-lock.json`, `npm ci`, then typecheck, test, build.

## Guardrail invariants preserved

- **Fraud hard stop has no override path.** The frontend exposes no field, query
  parameter, or form control that reaches a guardrail decision. The review-resolve form
  submits an operator note and a resolution, which the backend applies through the same
  engine.
- **Every action still routes through the decision engine.** The two action-capable
  routes are `POST /events` and `POST /review-queue/{id}/resolve`; both were already
  engine-gated and are unchanged by this phase.
- **Guardrails still sit between scoring and execution.** Nothing about scoring or
  execution moved. The frontend reads results and submits inputs; it computes no score,
  chooses no action, and holds no gateway credential.
- **No new privilege.** The proxy forwards the caller's own token and adds nothing, so
  the frontend cannot exceed the operator behind it.

## Verification

`npm run verify` (typecheck → tests → build) is green from a clean tree — no `.next`,
no `next-env.d.ts`:

```text
tsc --noEmit                     exit 0
vitest run                       70 passed (5 files)
next build                       compiled successfully, 20 routes
```

Unit tests cover the pure rules, which are the ones where a mistake is silent:

- `tests/access.test.ts` — role ranking, fail-closed on an unknown role, `/users` stays
  behind `ADMIN`, an unclassified route is denied by default.
- `tests/proxy-allowlist.test.ts` — `/auth/token` and `/webhooks/razorpay` are refused
  by every rule, method and shape are both part of the rule, traversal is rejected, a
  path that merely starts with an allowed one is not admitted.
- `tests/session.test.ts` — codec round trip and every fail-closed branch; cookie is
  httpOnly, `SameSite=Strict`, and `Secure` unless explicitly disabled.
- `tests/format.test.ts` — a missing value never renders as zero; a real zero score
  still renders as `0.0000`; an unrecognised action gets a neutral tone.
- `tests/types.test.ts` — the action list matches the backend enum, and there is no
  `NO_ACTION` sentinel.

The backend suite was re-run unchanged: **246 passed**. No existing test was modified.

### Container, verified by running it

`docker build ./frontend` succeeds. The image was started and exercised:

```text
GET  /login                     200
GET  /                          307 → /login
GET  /overview   (no session)   307 → /login
GET  /api/backend/metrics       401 {"detail":"Not signed in."}
POST /api/backend/auth/token    401 {"detail":"Not signed in."}
POST /api/webhooks/razorpay     401 {"detail":"Not signed in."}
```

Response headers carried `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`, and the CSP from `next.config.ts`; `X-Powered-By` was
absent. With no session the proxy answers 401 before it consults the allowlist — the
allowlist refusal itself is what the unit tests pin, not this smoke run.

`docker compose config` parses with the new `frontend` service. The full stack was
**not** brought up end to end in this phase; a signed-in browser session against the
live API is exercised in Phase 14's manual verification.

## Issues found and fixed

- **`vitest.config.ts` could not load.** Vitest resolved it as CommonJS (the package has
  no `"type": "module"`), and `vitest/dist/config.cjs` requires an ESM-only dependency.
  Renamed to `vitest.config.mts`.
- **A phantom `NO_ACTION` action.** Two ingestion surfaces compared
  `result.action === "NO_ACTION"`, which typecheck caught as impossible: the backend enum
  has no such member, and a refused guardrail returns the *forced* action instead. Both
  now use `isWithheld()`, so the withheld rendering is driven by what the backend
  actually sends. `tests/types.test.ts` locks the rule.
- **A wrong test expectation, not a wrong formatter.** `Intl.NumberFormat` does not throw
  on a well-formed unknown currency code — it uses the code as the symbol, separated by a
  non-breaking space. The test was corrected to assert real behaviour, and a second case
  covers the malformed code that does hit the fallback.
- **`tsconfig.json` rewritten by the build.** `next build` sets `jsx: react-jsx` and adds
  `.next/dev/types/**/*.ts`; both are committed so CI starts from the same config and
  does not see a dirty tree.

## Scope & limitations

- Streamlit is unchanged and still supported. Nothing was removed.
- No tests render React. The pure rules are unit-tested and the container is
  smoke-tested; component rendering is covered only by the typecheck and the build's page
  data collection.
- `RAZORPAY_WEBHOOK_SECRET` must be present for the webhook simulator page. Without it
  that route returns 503 rather than signing with a publicly known default.
- No new safety property was added here and none was moved. Every guardrail still sits in
  the backend, between scoring and execution.
