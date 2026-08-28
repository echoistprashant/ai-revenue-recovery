# Phase 12 — Authentication, Roles, Tenant Isolation & Human Review

## Objective

Close the largest remaining gap between this system and a deployable one: until now
every route was open. Anyone who could reach the port could ingest payment events,
read another customer's failure history, or flush the recovery queue. This phase adds
authentication, ranked roles, per-tenant data isolation, transport and abuse controls,
and the human review workflow the high-value guardrail has been escalating into since
Phase 3 — with the fraud hard stop and the retry cap explicitly out of reach of every
role, including `ADMIN`.

## Why this was needed

The system decides on money. Three things followed from having no auth:

1. **No caller identity.** The audit log recorded what was decided and why, but never
   *who* asked for it. "Every decision is auditable" was only half true.
2. **No isolation.** One SQLite/PostgreSQL database held every event, and any request
   read all of it. Multi-tenant deployment was impossible, and the idempotency key
   `(payment_id, attempt_id)` was globally unique — gateway payment identifiers are
   only unique within an account, so one tenant's event could silence another's.
3. **Nowhere for an escalation to go.** `HIGH_VALUE_REVIEW` produced
   `ESCALATE_TO_HUMAN` and then the case sat in `ESCALATED` forever. There was no
   queue, no reviewer, and no way to close it.

## Implemented

### Password and token primitives (`src/revenue_recovery/security.py`)

- bcrypt hashing used directly, not through `passlib` — `passlib` 1.7.4 breaks
  against bcrypt ≥ 4.1 while reading `bcrypt.__about__.__version__`, and this needs
  two functions, not a framework.
- Passwords must be at least 12 characters, and longer than 72 bytes is refused
  rather than silently truncated, which is what bcrypt does to the input otherwise.
- `TokenSigner` issues and verifies HS256 JWTs. `verify` requires `exp`, so a token
  minted without an expiry is rejected instead of lasting forever.
- **The signing key fails closed.** In production a missing key, or one shorter than
  32 characters, raises at construction and the API does not boot. In development an
  ephemeral key is generated per process: tokens stop working after a restart, which
  is inconvenient in exactly the way a shared default key is not.

### Accounts and roles (`src/revenue_recovery/auth.py`)

- `Role` is ranked — `VIEWER` (1) < `OPERATOR` (2) < `ADMIN` (3) — and `User.can`
  answers one question, so route protection is one `require(minimum)` dependency
  rather than per-route role lists that drift.
- `UserRepository` stores only bcrypt hashes, normalizes usernames to lowercase (so
  `Alice` and `alice` cannot both exist), records `last_login_at`, and supports
  deactivation, reactivation, and password replacement.
- Password strength is checked **before** any row is written, so a rejected weak
  password leaves no partial account behind.

### Route protection (`src/revenue_recovery/api.py`)

- `HTTPBearer(auto_error=False)` plus a `current_user` dependency that verifies the
  token and then **re-reads the account row on every request**. The token carries a
  username and nothing else that is trusted: deactivation and demotion take effect on
  the account's next call, not at token expiry.
- Minimums by route: reads (`/metrics`, `/history`, `/priority-cases`, `/audit-log`,
  `/review-queue`, `/decisions`, `/analyst`, `/experiments`, `/drift`,
  `/gateway-health`, `/recommendations`, `/operational-metrics`, `/tasks/stats`) are
  `VIEWER`; `/events`, `/review-queue/{id}/resolve`, `/communication`, and
  `/tasks/run-due` are `OPERATOR`; `/auth/users*` is `ADMIN`. `/health` stays open so
  a load balancer needs no credentials, and `/webhooks/razorpay` stays
  signature-authenticated because a gateway cannot hold a password.
- `POST /auth/token` issues a token; `GET /auth/me` reports the current identity.

### Tenant isolation

- `payment_events.tenant_id` scopes every read, and the idempotency key became
  `(tenant_id, payment_id, attempt_id)`.
- The audit log is isolated by joining to its event rather than carrying its own
  tenant column — one source of truth, so the two cannot disagree.
- Webhooks land in `DEFAULT_TENANT`. Inferring a tenant from payload contents would
  be a way to write into another tenant's data.
- `migrations/versions/2d3b442d364b_auth_roles_and_tenant_isolation.py` adds the
  `users` table and the tenant column, and rebuilds the unique index. It uses
  `batch_alter_table` so SQLite can rebuild the constraint.

### Transport and abuse controls (`src/revenue_recovery/rate_limit.py`)

- Fixed-window per-client request budget (`RATE_LIMIT_PER_MINUTE`, default 120) with a
  separate, much tighter budget for the login route (`LOGIN_RATE_LIMIT_PER_MINUTE`,
  default 10). Over-budget requests get 429 with `Retry-After`.
- `ENFORCE_HTTPS` (on by default in production) refuses plain HTTP with **403, not a
  redirect** — a redirect would already have carried the bearer token in clear text.
  `X-Forwarded-Proto` is honoured for deployment behind a TLS-terminating proxy.

### Human review queue

- `GET /review-queue` lists `ESCALATED` cases ordered by priority score;
  `POST /review-queue/{event_id}/resolve` closes one with `MANUAL_RECOVERED`,
  `WRITTEN_OFF`, or `MANUAL_RETRY`. A case that is not `ESCALATED` is refused with
  409, and the reviewer's username and note are written to the audit log.
- `MANUAL_RETRY` sets `human_review_approved` and re-runs the decision engine. That
  flag satisfies exactly one guardrail and is evaluated after the two that cannot be
  cleared (see below).

### Frontend (`dashboard/`)

- A login gate: `dashboard/app.py` renders nothing but the sign-in form until
  `POST /auth/token` succeeds. `SessionAPIClient` catches a 401 from *any* endpoint
  once, drops the token, and reruns on the login form, so no panel has to handle an
  expired session itself.
- The sidebar shows the signed-in username, role badge, tenant, and a sign-out button.
- `dashboard/access.py` holds the module→minimum-role map, so the menu hides what a
  role cannot use *and* the rule is testable without a Streamlit runtime. An
  unrecognised role ranks 0 and is shown nothing, so an older dashboard against a
  newer backend fails closed.
- Two new modules: **Human Review Queue** (queue table, case drill-down with scores,
  per-case audit trail, and — for operators only — the resolve form, which reports
  withheld-by-engine outcomes as such) and **User Administration** (account list,
  create, deactivate).
- **Audit & Decision History** gained a per-event audit-trail drill-down via
  `GET /audit-log?event_id=`.
- `scripts/create_user.py` bootstraps the first administrator. The password comes from
  a no-echo prompt or `REVENUE_RECOVERY_ADMIN_PASSWORD`, never a default: a default
  would be public, and a generated one would end up in shell history or CI logs.

## Guardrail invariants preserved

Authentication introduced two new ways to reach a financial action — the resolve route
and an authenticated ingest — so both were built to pass through the same engine:

- **`FRAUD_RISK_DECLINE` remains a hard stop with no override path, for every role.**
  `human_review_approved` is checked *after* the fraud stop and *after* the retry cap
  in `evaluate_guardrails`, so an approving reviewer — or any future caller that sets
  the flag — hits those refusals first. A fraud event lands in `STOPPED` and never
  enters the review queue at all; asking to resolve it returns 409 even for `ADMIN`.
- **The flag is never taken from input.** Only the resolve route sets it, after the
  caller's `OPERATOR` role has been verified. No request body or task payload can.
- **An approval does not execute anything by itself.** `MANUAL_RETRY` is re-decided by
  `DecisionEngine`, which can still withhold on the model's score, the retry cap, or
  an active gateway incident. The response reports `executed: false` and the case
  stays in the queue.
- **Guardrails still sit between scoring and the decision.** No new entry point calls
  an action directly; `/events`, the webhook, the queue executor, and the resolve
  route all go through `process_event` / `DecisionEngine`.
- **Every decision is now attributable.** The reviewer's username, resolution, and
  note are in the audit log alongside the reason, model version, and timestamp.

## Verification

**pytest: 246 passing.** 124 of those are in this phase's four new test files, plus
twelve added to existing files. No existing test was weakened or removed: the eleven
API tests whose signatures changed took an authenticated `client` fixture in place of
the bare `service`, keeping every assertion they already made.

- `tests/test_security.py` (17) — hashes contain no plaintext and are salted; verify
  rejects a case change, a suffix, and an empty password; a corrupt hash returns
  `False` instead of raising; short and over-72-byte passwords are refused; production
  refuses a missing and a short signing key; development generates a different key per
  process; tokens signed with another key, tampered, `alg: none`, expired, or missing
  `exp` all raise `TokenError`.
- `tests/test_auth.py` (17) — role ranking both directions, username normalization and
  collision, weak password rejected with no row written, authenticate accept/reject,
  `last_login_at`, a deactivated account refused with the correct password,
  reactivation, password replacement, and `list_users` tenant scoping.
- `tests/test_api_auth.py` (70) — every protected route refuses an anonymous caller;
  role matrix for viewer/operator/admin across the write routes; a deactivated
  account's live token 401s; a demoted account 403s its next operator call without
  re-login; two tenants on one database cannot see each other's events, priority
  cases, audit log, review queue, or analyst answers; login rate limiting; and the
  fraud hard stop verified from all three roles.
- `tests/test_guardrails.py` (12, +6) — human review satisfies the high-value rule and
  cannot clear the fraud stop, the retry cap, or an active incident; the decision
  engine threads the flag through unchanged.
- `tests/test_service.py` (6, +2) — an escalated case carries the model's view; a
  stopped case is not scored.
- `tests/test_api_client.py` (4, rewritten) — the dashboard client against the real app
  through a `TestClient`: full authenticated round trip, `password` absent from the
  create-user response, 401 → `AuthenticationRequiredError`, 403 → plain error.
- `tests/test_dashboard_access.py` (20, new) — the menu rule: a viewer is offered no
  write module but can still read the review queue, an operator gets the write modules
  but not administration, an admin gets all, and an unrecognised role gets nothing.
- `tests/test_migrations.py` (6, +2) — the migration scopes the idempotency key to the
  tenant, and accounts round-trip against a migrated database.

End-to-end behaviour confirmed by hand as well as by test: a loyal high-value customer
scored 0.7669 and the reviewer's `MANUAL_RETRY` executed and recorded `RECOVERED`; a
risky one scored 0.0130, the retry was withheld, and the case stayed `ESCALATED` with
`recovered_events` at 0.

## Scope & limitations

- **Rate limiting is in-process.** Two API replicas mean two independent budgets. This
  is documented rather than solved because solving it properly means shared state
  (Redis or equivalent), which is not approved and is not yet needed at one replica.
- **No refresh tokens or password-reset flow.** A session lasts
  `ACCESS_TOKEN_TTL_MINUTES` (default 60) and then requires signing in again;
  `scripts/create_user.py --reset-password` is the operator-side reset.
- **The dashboard holds its token in Streamlit session state**, which lives in server
  memory for the browser session. It is not written to a cookie or to disk.
- **Still open for Phase 14:** `razorpay_webhook_secret` still defaults to the publicly
  known `test_webhook_secret` in `config.py` rather than failing closed (the dashboard
  no longer hardcodes it — it reads `RAZORPAY_WEBHOOK_SECRET` from the environment);
  no webhook replay protection or event deduplication; no structured logging, backups,
  or secrets-manager integration; and the scikit-learn version pin
  (`>=1.7,<1.8`) does not match the 1.9.0 in this environment, which produces an
  `InconsistentVersionWarning` when loading the model.
- **PostgreSQL** remains exercised by construction only; no server was available here.
  The new migration uses `batch_alter_table`, which is a no-op outside SQLite.
