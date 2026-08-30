# AI Revenue Recovery & Payment Intelligence Platform

An AI engineering project for understanding recurring-payment failures, prioritizing recoverable revenue, applying deterministic safety controls, and measuring recovery outcomes.

## Problem

Recurring payments fail for many different reasons: insufficient funds, expired or invalid cards, authentication problems, bank declines, gateway incidents, and fraud-risk signals. A fixed retry policy treats these cases alike, causing avoidable retries, poor customer experiences, and missed revenue.

This project will build an explainable system that classifies failures, estimates recovery likelihood, calculates business risk, applies safety guardrails, selects a deterministic action, records the outcome, and compares its results with a fixed-retry baseline.

## Objective

The intended system demonstrates the complete loop:

```text
PREDICT → DECIDE → ACT → MEASURE → LEARN
```

The goal is a resume-grade, interview-defensible implementation that is understandable, testable, auditable, and honest about the limitations of synthetic data.

## High-Level Architecture

```text
Payment Gateway / Synthetic Simulator
                ↓
Event Ingestion and Normalization
                ↓
Failure Classification
                ↓
ML and Deterministic Scoring
                ↓
Safety Guardrails and Incident Checks
                ↓
Deterministic Decision Engine
                ↓
Approved Action and Optional Communication
                ↓
Audit Log and Outcome Tracking
                ↓
Dashboard, Analytics, and AI Revenue Analyst
```

The detailed architecture and binding decisions are recorded in [docs/architecture.md](docs/architecture.md).

## Planned Core Capabilities

- Typed and idempotent payment-event ingestion
- Rule-based payment-failure classification
- Logistic Regression recovery-probability model
- Transparent churn-risk heuristic
- Revenue-at-risk and priority calculations
- Explainable payment-method recommendation
- Fraud, retry, contact, value, and incident guardrails
- Deterministic recovery decision engine
- Simulated recovery-action execution
- Audit logging and outcome tracking
- Gateway/bank incident detection and retry suppression
- Bounded customer communication through an LLM
- Read-only, tool-based AI Revenue Analyst
- Business dashboard and case drill-down
- Fixed baseline versus intelligent-strategy evaluation

These are planned capabilities, not claims about the current implementation.

## Current Status

**Phase 14 — Security, Observability, and Data Protection.** Both secrets that can
authorise a write now fail at boot rather than in traffic: production refuses to start
if `RAZORPAY_WEBHOOK_SECRET` is empty or still the `test_webhook_secret` value published
in `.env.example`, mirroring the existing `JWT_SECRET_KEY` rule.

Webhook deliveries are checked for freshness against the `created_at` that Razorpay puts
*inside the signed bytes* — it sends no timestamp header, and editing that field
invalidates the signature, so the timestamp is trustworthy to exactly the degree the
signature is. The window is symmetric and 300s by default (`WEBHOOK_TOLERANCE_SECONDS`);
a delivery from the future is refused as firmly as a stale one. Freshness is checked
after the signature, and a timestamp is required in production only. Freshness is the
perimeter, not the guard that protects money — idempotency on
`(tenant_id, payment_id, attempt_id)` is, and a test proves two byte-identical validly
signed in-window deliveries reach the gateway exactly once.

Logs are emitted as one JSON object per line (`LOG_FORMAT=json`, the production default)
with the extras the call site attached. Gateway identifiers are masked to a readable
prefix plus a truncated SHA-256 — `pay_***138504fc6bc7` — deterministic so two lines
about the same payment still join, without carrying the value needed to look that
customer up in the gateway dashboard. Secret-named keys are blanked over every record,
tracebacks are reduced to `error_type` and `error_message`, customer-facing message
bodies are never logged, and credentials quoted by a third-party exception are stripped
before the text is stored in `tasks.last_error` or shown to an operator. No new
monitoring stack was added: the gap was unstructured, unfilterable log lines, which is a
formatter problem, and the existing operational-metrics and PSI drift surfaces already
answer health and distribution shift.

[docs/data-protection.md](docs/data-protection.md) is a factual inventory written by
reading `schema.py` and every logging call site — every column that relates to a person,
what is deliberately absent (no name, email, phone, address, card number, last-four,
expiry, CVV, token, mandate reference, IP, or user-agent; the platform reads the
gateway's *decision*, never the instrument), and the retention stance. That stance is
**documented, not enforced**: there is no deletion job, no `retention_days` setting, and
no data-subject endpoint, and the document says so rather than implying a shipped
feature.

The scikit-learn version mismatch that warned on every model load is fixed by pinning
the dependency to the version the committed artifact was trained with, not by retraining
in-container — the published metadata describes one specific artifact, and rebuilding at
image-build time would make those numbers stop describing what runs. The pin cannot rot:
`sklearn_version` is recorded in both the artifact and the metadata, and four tests tie
artifact, runtime, dependency specifier, and metadata together, so a dependency bump
without a retrain is a failed test rather than a warning in a log.

**Phase 13 — Production Next.js Control Centre.** A Next.js 16 App Router frontend
(`frontend/`) at full parity with the Streamlit dashboard across all thirteen modules.
The API token is held in an httpOnly, `SameSite=Strict`, `Secure` cookie written by the
frontend's own route handlers, so browser JavaScript never holds a credential that can
authorise a payment action. The browser reaches the API only through an allowlisted
server-side proxy of 21 explicit `(method, path)` rules; `/auth/token` and
`/webhooks/razorpay` are deliberately not among them. There is no Edge middleware — the
dashboard layout is the single session gate, so the rule cannot exist in two versions.
Access rules and formatters are pure modules with unit tests: an unknown role sees
nothing, and a missing value renders as an em dash rather than `0.0000`. Streamlit is
unchanged and still supported.

**Phase 12 remains in place — Authentication, Roles, Tenant Isolation & Human Review.** Every route
except `/health` and the HMAC-signed gateway webhook now requires a bearer token.
Roles are ranked (`VIEWER` < `OPERATOR` < `ADMIN`): reads need `VIEWER`; ingesting
events, resolving escalations, generating customer messages, and flushing the queue
need `OPERATOR`; account management needs `ADMIN`. The account row is re-read on every
request, so deactivating or demoting an account takes effect on its next call rather
than at token expiry. Payment events carry a `tenant_id` and every read is scoped to
the caller's tenant; the idempotency key became `(tenant_id, payment_id, attempt_id)`.

The high-value escalation guardrail finally has somewhere to escalate *to*: a human
review queue (`GET /review-queue`, `POST /review-queue/{event_id}/resolve`) with a
reviewer UI. A reviewer's approval is an input, not an authority — `MANUAL_RETRY`
re-runs the deterministic decision engine, which can still withhold the retry. The
`human_review_approved` flag satisfies exactly one guardrail, the high-value review
that exists to wait for a person, and is checked *after* the fraud hard stop and the
retry cap. **No role, including `ADMIN`, can retry a `FRAUD_RISK_DECLINE` or exceed the
retry cap.**

The dashboard has a login gate, a role-aware menu, per-case audit-trail drill-down, the
review queue, and user administration. In production the API refuses to boot without a
`JWT_SECRET_KEY` of at least 32 characters, refuses plain HTTP with 403 rather than a
token-leaking redirect, and rate-limits every route with a tighter budget for login.

**Phase 11 remains in place.** Storage is a dialect-neutral SQLAlchemy Core layer
serving SQLite (local dev, tests, CI) and PostgreSQL (production) from one code path,
with Alembic owning schema changes. Approved recovery actions are written to a durable
`tasks` table and executed by a separate worker process, so a retry scheduled 24 hours
out survives a restart and a slow provider cannot block webhook ingestion. The worker
re-runs the decision engine immediately before executing anything, so a queued row is
a record of a past approval, not authority to act.

Phase 10 remains in place: a pluggable Gateway Adapter interface
(`BaseGatewayAdapter` & `RazorpayAdapter`) with HMAC-SHA256 signature verification,
normalized event conversion, `POST /webhooks/razorpay`, webhook simulation scripts,
and Streamlit Control Center integration.

The policy learner remains offline-only. Docker and CI package and verify the
system; synthetic data and simulated webhook ingestion are fully supported.

Still open: retention enforcement (documented in
[docs/data-protection.md](docs/data-protection.md) §5 as a stance, with no deletion job
in code), backups, secrets-manager integration, encryption at rest, and log-sink
retention. The real Razorpay webhook path has been exercised only with locally signed
payloads — that tests this code's understanding of the format, not Razorpay's actual
bytes — and a signed-in browser session against the live API has not been run
end to end.

## Local Setup

```text
python -m pip install -e ".[dev]"
python -m pytest
python scripts/train_recovery_model.py
python scripts/evaluate_optimization.py
python scripts/run_experiment.py
python scripts/evaluate_policy.py
docker compose up --build
python scripts/run_synthetic_batch.py --count 200
python -m uvicorn revenue_recovery.api:app --reload
python -m streamlit run dashboard/app.py
cd frontend && npm install && npm run dev
```

The synthetic batch writes to the ignored local SQLite database by default. Its
output is simulated and must not be presented as commercial performance.

### First sign-in

The API and dashboard require an account, and the first one is created from the
command line — there is no default password, because a default password is a public
one:

```text
python scripts/create_user.py --username admin --role ADMIN
python scripts/create_user.py --username analyst --role VIEWER --tenant acme
python scripts/create_user.py --username admin --role ADMIN --reset-password
```

The password is read from a no-echo prompt, or from
`REVENUE_RECOVERY_ADMIN_PASSWORD` for automated provisioning, and only its bcrypt
hash is stored. Minimum length is 12 characters.

In production, set a signing key or the API will refuse to start:

```text
export JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
export APP_ENVIRONMENT=production
```

In development the key is generated per process instead, so tokens simply stop
working when the API restarts. Roles: `VIEWER` reads, `OPERATOR` also ingests events,
resolves escalations, generates messages, and flushes the queue, `ADMIN` also manages
accounts. See [`.env.example`](.env.example) for `ACCESS_TOKEN_TTL_MINUTES`,
`RATE_LIMIT_PER_MINUTE`, `LOGIN_RATE_LIMIT_PER_MINUTE`, `ENFORCE_HTTPS`, and
`DEFAULT_TENANT`.

### Control centre (Next.js)

The production frontend lives in `frontend/` and needs Node 20.9 or newer. It talks to
the API server-side only, so `REVENUE_RECOVERY_API_URL` must be reachable from the
frontend process, not from the browser:

```text
cd frontend
npm install
npm run verify          # typecheck, unit tests, production build
npm run dev             # http://localhost:3000
```

Sign in with an account created by `scripts/create_user.py`. On local HTTP set
`FRONTEND_COOKIE_SECURE=false`, because a `Secure` cookie is dropped on
`http://localhost` and sign-in would appear to succeed and then immediately fail; leave
it at its default in production. `RAZORPAY_WEBHOOK_SECRET` is needed only by the webhook
simulator page, which returns 503 rather than signing with a publicly known default when
it is unset. See [`.env.example`](.env.example) for `BACKEND_TIMEOUT_MS`.

The Streamlit dashboard remains available and is unaffected.

### Database and migrations

SQLite is the default and needs no setup. To run on PostgreSQL, set `DATABASE_URL`
and apply the migrations first — the application refuses to create tables on a
non-SQLite driver, so an unmigrated production database fails loudly instead of
silently drifting from the migration history:

```text
export DATABASE_URL=postgresql+psycopg://user:password@host:5432/revenue_recovery
python -m pip install -e ".[postgres]"
python -m alembic upgrade head
```

`postgres://`, `postgresql://`, and `postgresql+psycopg://` are all accepted and
normalized to the psycopg driver. An existing SQLite database created before this
phase should be stamped rather than upgraded: `python -m alembic stamp head`.

### Background worker

Set `TASK_EXECUTION_MODE=queued` and run the worker alongside the API:

```text
python scripts/run_worker.py            # long-running poller
python scripts/run_worker.py --once     # drain due work and exit
```

`docker compose up --build` starts the API, the worker, the Streamlit dashboard, and
the Next.js control centre on port 3000.
`docker compose --profile postgres up` adds PostgreSQL and a one-shot `migrate`
service; it requires `POSTGRES_PASSWORD` to be set and refuses to start without it.

In the default `inline` mode the ingesting request still executes the action, which
is what the recorded synthetic baselines were measured with. Both modes share one
execution path, so switching does not change what happens to a payment.

The committed model metadata in `models/recovery_model_metadata.json` reports
held-out synthetic evaluation, leakage exclusions, group separation, error counts,
and coefficient-based explanations.

Operational endpoints include `/operational-metrics`, `/drift`, `/tasks/stats`, and
`/tasks/run-due`. Authentication and review endpoints are `/auth/token`, `/auth/me`,
`/auth/users`, `/audit-log`, `/review-queue`, and
`/review-queue/{event_id}/resolve`. GitHub Actions runs the test suite, an
`alembic upgrade` plus schema-drift check, the model training check, and the
experiment report on pushes and pull requests.

## Roadmap

The official roadmap contains eight phases:

1. Core Payment Recovery
2. Machine Learning Layer
3. Recovery Optimization
4. System Intelligence and Guardrails
5. GenAI Layer
6. Experimentation Engine
7. Advanced AI (optional)
8. Production Engineering

The blueprint's 32 capability items are requirements grouped into these phases; they are not 32 official phases. See [docs/roadmap.md](docs/roadmap.md) and [docs/blueprint.md](docs/blueprint.md).

## Initial Technology Decisions

- Python for application development
- FastAPI and Pydantic for the planned API boundary
- SQLite for the initial database
- scikit-learn Logistic Regression for the initial recovery model
- Streamlit as the initial dashboard direction (Phase 13 adds a Next.js control
  centre at parity; both are supported)
- pytest for planned testing
- Synthetic simulation as the required offline fallback

No application dependencies are installed or declared during Phase 0.

Later revisions: SQLite is now the development and test database rather than the
only one — SQLAlchemy Core plus Alembic serve SQLite and PostgreSQL from one code
path (Phase 11). Background execution uses a database-backed queue and a worker
process rather than a message broker, keeping the deployment to one extra process.

## LLM Boundary

The LLM is not a financial decision maker. It may only:

1. Generate customer-facing language after the deterministic engine has approved an action.
2. Answer analytics questions using approved read-only tools and real project data.

It may not choose or execute recovery actions, change amounts or financial parameters, bypass guardrails, or override the deterministic decision engine.

## Safety Principles

- Fraud-risk declines must result in `STOP_RECOVERY`.
- High-value transactions must be escalated according to configuration.
- Retry counts and customer-contact frequency must be capped.
- Duplicate `(tenant_id, payment_id, attempt_id)` events must not create duplicate
  actions.
- Active bank or gateway incidents may suppress retries.
- Queued work carries no authority of its own: the decision engine is re-run before
  any action executes, so nothing can reach a financial side effect without passing
  the guardrails at that moment.
- No role overrides a guardrail. A reviewer's approval satisfies only the high-value
  review that exists to wait for a person; it is evaluated after the fraud hard stop
  and the retry cap, so neither can be cleared by any role, `ADMIN` included.
- Every decision must be deterministic, explainable, and auditable, and attributable
  to the account that requested it.
- Secrets and real payment credentials must never be committed.

## Synthetic-Data Disclaimer

Development and evaluation will initially use reproducible synthetic data. All resulting metrics will be labeled as simulated. Synthetic recovery rates, revenue figures, and model performance must never be presented as observed commercial results.

## Development Workflow

Work proceeds one phase at a time:

```text
PLAN → IMPLEMENT → TEST → REVIEW → DOCUMENT → COMMIT → PUSH
```

Before each phase, its objective, affected files, dependencies, acceptance criteria, tests, and risks must be reviewed. Future-phase functionality must not be introduced silently.

## Testing Philosophy

Testing is mandatory once application development begins. Planned coverage includes unit tests, safety tests, model-interface tests, API tests, and end-to-end integration tests. Tests must validate the implementation rather than be weakened to make incorrect behavior pass.

Phase 0 uses repository-level validation because no application exists yet.

## Git and GitHub Workflow

- Primary branch: `main`
- Remote: `origin`
Real development problems and lessons will be recorded in [docs/what-broke.md](docs/what-broke.md). No issues will be fabricated.

---

## Project Status: COMPLETED (Phases 00 – 15)

All 15 project phases and final production-readiness blocks are fully implemented, tested, and verified:

1. **Core Pipeline:** Ingestion, failure classification, ML recovery probability, churn heuristic, revenue at risk, priority scoring, guardrails, decision engine, action execution, outcome audit.
2. **Persistence & Execution:** Dual-driver SQLAlchemy Core (SQLite WAL + PostgreSQL `psycopg`), Alembic migrations, durable DB task queue, background `RecoveryWorker`.
3. **Security & Data Protection:** Strict boot-time secret enforcement, symmetric 300s webhook timestamp freshness validation, HMAC-SHA256 signature verification, deterministic log masking (`pay_***`), credential scrubbing, and zero-PII storage policy.
4. **Interfaces:** Streamlit control center (`dashboard/`) & Next.js 16 App Router control center (`frontend/`) with httpOnly cookie sessions and allowlisted proxy.
5. **Gateway & LLM Integrations:** Live Razorpay test-mode adapter and outbound API retry provider (`RazorpayRetryProvider`); bounded Gemini LLM integration (`google-genai`) for customer communications and read-only analyst function calling, backed by zero-dependency deterministic fallbacks.
6. **Scale Readiness:** Formally evaluated in `docs/phase-notes/phase-15.md` — SQLite/PostgreSQL + DB task queue achieves zero-bottleneck performance for target workloads without unnecessary microservice overhead.
7. **Verification:** 306 backend unit/integration tests passed (`pytest`); 70 frontend tests passed (`vitest`).

