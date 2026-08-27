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

## Decision 7 — Initial Retry Timing

The initial system will use fixed or failure-category-based retry windows. Personalized retry-timing ML belongs to the later Recovery Optimization phase.

## Decision 8 — Deferred Infrastructure

Kafka, Redpanda, Redis, Celery, Kubernetes, microservices, complex MLOps, vector databases, retrieval-augmented generation, and reinforcement learning are not introduced during Phase 0. They remain deferred unless explicitly approved later.

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
