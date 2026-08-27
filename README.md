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

**Phase 11 — Production Persistence & Durable Background Execution.** Storage moved
from direct `sqlite3` calls to a dialect-neutral SQLAlchemy Core layer that serves
SQLite (local dev, tests, CI) and PostgreSQL (production) from one code path, with
Alembic owning schema changes. Approved recovery actions are no longer executed
inside the ingesting request: they are written to a durable `tasks` table and
executed by a separate worker process, so a retry scheduled 24 hours out survives a
restart and a slow provider cannot block webhook ingestion.

The worker re-runs the deterministic decision engine immediately before executing
anything, so a queued row is a record of a past approval, not authority to act — the
retry cap, high-value escalation, incident suppression, and the `FRAUD_RISK_DECLINE`
hard stop all still apply at execution time.

Phase 10 remains in place: a pluggable Gateway Adapter interface
(`BaseGatewayAdapter` & `RazorpayAdapter`) with HMAC-SHA256 signature verification,
normalized event conversion, `POST /webhooks/razorpay`, webhook simulation scripts,
and Streamlit Control Center integration.

The policy learner remains offline-only. Docker and CI package and verify the
system; synthetic data and simulated webhook ingestion are fully supported.

Not yet done: the API has no authentication (Phase 12), and structured logging,
backups, secrets management, and webhook fail-closed behaviour are outstanding
(Phase 14).

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
```

The synthetic batch writes to the ignored local SQLite database by default. Its
output is simulated and must not be presented as commercial performance.

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

`docker compose up --build` starts the API, the worker, and the dashboard.
`docker compose --profile postgres up` adds PostgreSQL and a one-shot `migrate`
service; it requires `POSTGRES_PASSWORD` to be set and refuses to start without it.

In the default `inline` mode the ingesting request still executes the action, which
is what the recorded synthetic baselines were measured with. Both modes share one
execution path, so switching does not change what happens to a payment.

The committed model metadata in `models/recovery_model_metadata.json` reports
held-out synthetic evaluation, leakage exclusions, group separation, error counts,
and coefficient-based explanations.

Operational endpoints include `/operational-metrics`, `/drift`, `/tasks/stats`, and
`/tasks/run-due`. GitHub Actions runs the test suite, an `alembic upgrade` plus
schema-drift check, the model training check, and the experiment report on pushes
and pull requests.

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
- Streamlit as the initial dashboard direction
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
- Duplicate `(payment_id, attempt_id)` events must not create duplicate actions.
- Active bank or gateway incidents may suppress retries.
- Queued work carries no authority of its own: the decision engine is re-run before
  any action executes, so nothing can reach a financial side effect without passing
  the guardrails at that moment.
- Every decision must be deterministic, explainable, and auditable.
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
- Repository: <https://github.com/echoistprashant/ai-revenue-recovery>
- Commit format: `<type>(phase-XX): <short description>`
- Each completed phase must be tested, reviewed, documented, committed, pushed, and verified before the next phase begins.

Real development problems and lessons will be recorded in [docs/what-broke.md](docs/what-broke.md). No issues will be fabricated.
