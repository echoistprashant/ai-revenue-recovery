# Architecture Decisions

## Status

This document records decisions approved before application development begins. It describes intended boundaries and does not claim that application functionality currently exists.

The source priority is:

1. [Blueprint](blueprint.md)
2. Current phase in the [roadmap](roadmap.md)
3. Existing architecture and explicit decisions in this document
4. The simplest solution satisfying the approved requirements

## Intended System Boundary

```text
Payment Gateway / Synthetic Simulator
                ↓
Validation, Normalization, and Idempotent Persistence
                ↓
Rule-Based Failure Classification
                ↓
Immediate Non-Negotiable Safety Checks
                ↓
Feature Engineering and Scoring
                ↓
Incident and Operational Guardrails
                ↓
Deterministic Decision Engine
                ↓
Approved Action
             ↙           ↘
Action Executor      Optional LLM Communication
             ↘           ↙
          Audit and Outcome Tracking
                    ↓
          Dashboard and Read-Only Analytics
                    ↓
              AI Revenue Analyst
```

Responsibilities for ingestion, classification, features, prediction, risk calculations, incidents, guardrails, decisions, execution, audit, analytics, and LLM interaction must remain separate.

## Decision 1 — 32 Capabilities and 8 Roadmap Phases

The project contains 32 capability items in the blueprint, 8 official roadmap phases, and granular execution checkpoints used internally. The 32 capabilities are not the official roadmap phases.

```text
Blueprint → 32 Capabilities → 8 Official Roadmap Phases → Granular Execution Checkpoints
```

The eight roadmap phases remain the primary delivery structure. Repository initialization is identified separately as Phase 0.

## Decision 2 — Payment Attempt Identity

The future canonical payment-event model must include `payment_id` and `attempt_id`. Idempotency must use `(payment_id, attempt_id)`. The payment schema is not implemented in Phase 0.

## Decision 3 — Churn Risk

The initial scoped system will use the documented transparent churn-risk heuristic. It will not present that score as a trained model or calibrated probability, and no ML-performance metrics will be claimed for it. A trained churn model remains outside the initial core scope.

## Decision 4 — Recovery Model

The initial recovery-probability model will be Logistic Regression through a stable prediction interface. XGBoost, LightGBM, or other advanced models are optional later comparisons and must not be introduced prematurely.

## Decision 5 — Fraud Hard Stop

Fraud hard-stop evaluation must occur before normal automated recovery decisioning:

```text
FRAUD_RISK_DECLINE → STOP_RECOVERY
```

Neither an ML score nor an LLM response may override this result. The guardrail itself is not implemented in Phase 0.

## Decision 6 — Initial Database

SQLite is the initial database. PostgreSQL is not introduced during Phase 0, and no database or table is created during this phase.

Revised in Phase 11: see Decision 13.

## Decision 7 — Initial Retry Timing

The initial system will use fixed or failure-category-based retry windows. Personalized retry-timing ML belongs to the later Recovery Optimization phase.

## Decision 8 — Deferred Infrastructure

Kafka, Redpanda, Redis, Celery, Kubernetes, microservices, complex MLOps, vector databases, retrieval-augmented generation, and reinforcement learning are not introduced during Phase 0. They remain deferred unless explicitly approved later.

This still holds in Phase 11. Durable background execution was needed, and it was built as a database table plus a worker process (Decision 14) rather than by adopting a broker or task framework, so nothing on the deferred list was introduced.

## Decision 9 — LLM Boundary

The LLM is not the financial decision authority. It must never choose recovery actions, trigger retries, change payment amounts, modify financial parameters, bypass guardrails, override the deterministic decision engine, execute payment actions, or approve or reject transactions.

It is allowed only to generate customer-facing communication after an action has been approved and answer analytics questions using approved read-only tools and real project data. Financial interfaces must not be exposed as LLM tools.

```text
ML + Rules → Deterministic Decision Engine → Approved Action → LLM → Communication
```

## Decision 10 — Synthetic Data and Claims

All synthetic experiments must be clearly labeled as simulated. Synthetic recovery rates, recovered revenue, model performance, incident behavior, or business improvements must never be presented as observed commercial performance. No synthetic data is generated during Phase 0.

## Decision 11 — Operational Control Center Frontend

The user-facing Operational Control Center is implemented using Streamlit (`dashboard/app.py`) backed by an isolated `APIClient` (`dashboard/api_client.py`). The frontend remains strictly presentation and orchestration, while business logic, decision rules, ML scoring, guardrails, and audit logging reside exclusively in the FastAPI backend service.

## Decision 12 — Payment Gateway Adapter Pattern & Signature Security

Provider-specific payment gateway structures (such as Razorpay webhooks) are isolated behind an abstract `BaseGatewayAdapter` interface (`revenue_recovery.adapters`). Cryptographic HMAC-SHA256 signature verification (`X-Razorpay-Signature`) is enforced on webhook listener endpoints (`POST /webhooks/razorpay`) before payload parsing or service processing. Unsigned or invalid signature payloads are rejected with HTTP 401 Unauthorized.

## Decision 13 — Dual-Driver Persistence with Migrations

Storage is accessed through SQLAlchemy Core (`revenue_recovery.database`) against a
single schema definition (`revenue_recovery.schema.METADATA`). SQLite serves local
development, tests, and CI so those need no infrastructure; PostgreSQL
(`postgresql+psycopg`) serves production, selected by `DATABASE_URL`. All SQL stays
dialect-neutral: named bind parameters, `INSERT ... RETURNING`, no vendor syntax.

Alembic owns schema change. `Database.initialize()` creates tables only on SQLite;
on any other driver it verifies the tables exist and refuses to start otherwise.
Implicit table creation in production would let a process boot against a database no
migration had touched, after which the metadata and the migration history would
drift apart without anyone noticing.

Timestamps are stored as UTC ISO-8601 text (`revenue_recovery.clock`). Text behaves
identically on both drivers, and a single UTC offset keeps lexicographic ordering
equal to chronological ordering, which the queue's due-work comparison depends on.

## Decision 14 — Durable Background Execution Without a Broker

Recovery actions are not executed inside the request that ingested the event. The
approved action is written to a `tasks` table and executed by a separate worker
process (`revenue_recovery.worker`, `scripts/run_worker.py`). A delayed retry
therefore survives a restart, and a slow notification provider cannot block webhook
ingestion. Claiming is a conditional `UPDATE ... WHERE status = 'PENDING'`, which
needs no dialect-specific locking hint and so behaves the same on both drivers.

The queue does not sit beside the decision engine as a second source of authority.
`ActionExecutor` re-runs the deterministic engine immediately before performing any
side effect and withholds the action if the engine no longer approves it. Time
passes between approval and execution — a retry cap may now be reached, an incident
may now be active, the event may have been re-classified — so the approval is
re-established rather than assumed. `FRAUD_RISK_DECLINE` is refused at execution
time with no override path, and enqueueing is unique per `(event_id, task_type)`, so
event-level idempotency extends to execution. Each task writes a `TASK_<type>` audit
row recording the re-validated action and whether it executed.

Inline execution remains the default so the recorded synthetic baselines keep their
numbers; both modes share one execution path.

## Decision 15 — Built-in JWT Authentication with Ranked Roles

Authentication is built into the application (`revenue_recovery.security`,
`revenue_recovery.auth`) rather than delegated to an external identity provider: the
system has three roles and one login form, and an external provider would add a
network dependency and a second failure mode to a surface that small. Access tokens
are HS256 JWTs; passwords are stored only as bcrypt hashes.

The signing key fails closed. In production the API refuses to boot without
`JWT_SECRET_KEY` of at least 32 characters, because a default signing key is a
credential everyone with the source can mint tokens from. In development an ephemeral
key is generated per process, so tokens stop working on restart instead of being
signed by something guessable.

Roles are ranked — `VIEWER` (1) < `OPERATOR` (2) < `ADMIN` (3) — and every route
declares a minimum through one `require(minimum)` dependency, so a new route cannot
accidentally be less protected than its neighbours. Reads are `VIEWER`; ingesting
events, resolving escalations, generating customer messages, and flushing the queue
are `OPERATOR`; account management is `ADMIN`. The account row is re-read from the
database on every request rather than trusting the token's claims, so deactivation
and demotion take effect on the account's next call instead of at token expiry.

Role rank never reaches the guardrails. `ADMIN` administers accounts; it does not
acquire a path to retry a `FRAUD_RISK_DECLINE` or to exceed the retry cap. Those
refusals are evaluated before the human-review flag is even consulted.

Transport and abuse controls sit in middleware: plain-HTTP requests are refused with
403 rather than redirected, because a redirect has already carried the bearer token
in clear text; and a fixed-window per-client rate limit applies to every route, with
a separate tighter budget for the login route.

## Decision 16 — Tenant Isolation and the Human Review Queue

Every payment event carries a `tenant_id`, and every read is scoped by the caller's
tenant. The idempotency key became `(tenant_id, payment_id, attempt_id)`: gateway
payment identifiers are only unique within an account, so a global key would let one
tenant's event silence another's. The audit log is isolated by joining to its event
rather than by carrying a duplicate tenant column, so the two can never disagree.
Gateway webhooks authenticate by HMAC signature and carry no tenant of their own, so
they land in the configured `DEFAULT_TENANT` — inferring a tenant from payload
contents would be a way to write into another tenant's data.

The high-value escalation guardrail now has a place to escalate *to*: `ESCALATED`
cases form a review queue (`GET /review-queue`), ordered by priority score, closed by
`POST /review-queue/{event_id}/resolve` with `MANUAL_RECOVERED`, `WRITTEN_OFF`, or
`MANUAL_RETRY`.

A reviewer's approval is an input to the decision, not an authority over it.
`MANUAL_RETRY` re-submits the case to the deterministic decision engine with
`human_review_approved` set, and that flag satisfies exactly one guardrail — the
high-value review that exists to wait for a person. It is evaluated *after* the fraud
hard stop and the retry cap, so an approving reviewer still cannot retry a fraud
decline or exceed the cap, and the engine can still withhold the retry on the model's
score. The flag is never read from a task payload or a request body; only the resolve
route sets it, after the caller's `OPERATOR` role has been checked.

## Decision 17 — A Backend-for-Frontend, Not a Browser Client

The Next.js control centre never holds a credential that can authorise a payment
action. Sign-in posts to the frontend's own route handler, which calls `/auth/token`
server-side and stores the bearer token in an httpOnly, `SameSite=Strict`, `Secure`
cookie. Browser JavaScript cannot read it, so an XSS in a dependency can at most make
requests the signed-in operator could already make, and a cross-site form post carries
no session at all. The alternative — a token in `localStorage` and `fetch` straight to
the API — makes any script on the page a payment-capable client.

The cookie is not signed, because there is nothing in it worth forging. The only field
the backend trusts is the token, which is itself signed and re-checked against the
account row on every request. Editing `role` in the cookie changes which navigation
links get rendered and nothing else; the API answers 403 on its own authority.

The browser reaches the API only through an allowlisted proxy: 21 explicit
`(method, path-pattern)` rules, with `..` refused before a URL is built. The proxy
attaches the caller's own token and adds no privilege, so it can never exceed the
operator behind it. The allowlist exists so it is not a general-purpose tunnel — a new
endpoint has to be admitted on purpose. `/auth/token` and `/webhooks/razorpay` are
deliberately absent: login keeps its issued token server-side, and the webhook is
signed in a route handler so its HMAC secret never reaches the browser.

Two allowlisted routes can lead to a payment action, `POST /events` and
`POST /review-queue/{event_id}/resolve`. Both were already engine-gated; the frontend
adds no new path to an action, no field that skips a guardrail, and no scoring of its
own.

There is no `middleware.ts`. The dashboard route group's server layout is the single
session gate — duplicating the same rule into the Edge runtime would create two copies
that can drift, and only one of them is the one that renders the page.

Access rules live in a plain data table (`lib/access.ts`) with no framework imports, so
they are unit-testable, and an unrecognised role ranks 0 and sees nothing: an older
frontend against a newer backend fails closed. Formatters are total — a missing value
renders as an em dash and an unscored case as "not scored", never as `0.0000`, because
a console that reports money must not turn absent data into a confident zero.
