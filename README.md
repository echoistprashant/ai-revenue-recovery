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

**Phase 2 — Machine Learning Layer.** The repository contains the Phase 1 recovery baseline plus a versioned Logistic Regression recovery model, a transparent churn-risk heuristic, configurable revenue-at-risk calculation, deterministic priority scoring, and ranked priority-case APIs/dashboard output.

Personalized recovery optimization, the centralized decision engine, advanced guardrails and incident detection, LLM integrations, and experimentation are not implemented yet. Phase 2 scores cases but does not allow model probability to choose or execute a financial action.

## Local Setup

```text
python -m pip install -e ".[dev]"
python -m pytest
python scripts/train_recovery_model.py
python scripts/run_synthetic_batch.py --count 200
python -m uvicorn revenue_recovery.api:app --reload
python -m streamlit run dashboard/app.py
```

The synthetic batch writes to the ignored local SQLite database by default. Its output is simulated and must not be presented as commercial performance.

The committed model metadata in `models/recovery_model_metadata.json` reports held-out synthetic evaluation, leakage exclusions, group separation, error counts, and coefficient-based explanations.

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
