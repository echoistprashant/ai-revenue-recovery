# AI Revenue Recovery & Payment Intelligence Platform — Project Context

## 1. What This Is

A deterministic, ML-scored, LLM-bounded system for recovering failed recurring payments.
Core philosophy: PREDICT → DECIDE → ACT → MEASURE → LEARN.

This is NOT a chatbot that makes payment decisions. It is a payment-recovery system where
ML produces signals (probabilities, scores), a deterministic decision engine converts those
signals into one of a fixed set of actions, and an LLM is used ONLY for two narrow, bounded
purposes (see Section 2). All current data is synthetic — there is no real payment gateway,
real bank, or real customer data connected yet.

## 2. Non-Negotiable Design Invariants — DO NOT VIOLATE THESE WHILE EXTENDING THE SYSTEM

These principles have been enforced since Phase 0 and are covered by existing tests. Any new
work (frontend, auth, real payment integration, etc.) MUST preserve them:

- The LLM can NEVER decide, trigger, approve, or reject a financial action. It can only
  (a) write a customer-facing message for an action that a deterministic engine already
  approved, or (b) answer analytics questions using read-only tool calls over real computed
  data — it must never state a number it didn't get from a tool call.
- FRAUD_RISK_DECLINE is a hard stop with no override path — not by config, not by a human
  admin flag, not by an LLM suggestion. This must remain true even after auth/roles are added.
  a human ROLE having override permission is fine, an automated bypass is not.
  a human role having override permission is fine; an automated bypass is not.
- Guardrails (retry cap, high-value escalation, contact cooldown, gateway-incident
  suppression, idempotency) sit BETWEEN scoring and the decision engine and cannot be
  skipped by any new entry point (new API route, new frontend action, new integration).
  If you add a new way to trigger a recovery action, it must still pass through the same
  decision engine — never a direct action call.
- Offline policy learning (Phase 7) does not get promoted to live/self-modifying behavior
  without this being an explicit, discussed decision — not an incidental side effect of
  adding a "retrain" button somewhere.
- Every decision must remain auditable: reason, model version, timestamp, outcome.

## 3. Current State — Phase 0 through Phase 8 are COMPLETE and tested (build on this, don't
## rebuild it)

### Phase 0 — Project Initialization
Repository/architecture foundation only, no functionality. Established docs/ (README,
architecture.md, what-broke.md, phase-notes), .gitignore, .env.example. Locked early
decisions: SQLite as the initial DB, Logistic Regression as the recovery-model baseline,
fraud hard-stop as non-negotiable, LLM never a financial decision-maker, and explicitly
decided AGAINST premature dependencies (Kafka, Redis, Celery, Kubernetes, RAG/vector DB, RL)
as core requirements at this stage.

### Phase 1 — Core Payment Recovery Foundation (BACKEND + basic frontend)
- FastAPI app, typed Pydantic payment events, SQLite persistence
- Endpoints: POST /events, GET /health, GET /metrics
- Idempotency via (payment_id, attempt_id)
- 9-category failure classification: INSUFFICIENT_FUNDS, EXPIRED_CARD, INVALID_CARD,
  AUTHENTICATION_FAILURE, BANK_DECLINED, GATEWAY_OR_NETWORK_FAILURE, FRAUD_RISK_DECLINE,
  PAYMENT_METHOD_FAILURE, TEMPORARY_BANK_ISSUE
- Fixed retry delays (1h / 6h / 24h), deterministic synthetic outcomes
- Audit, decision, and outcome records; seeded synthetic payment generator
- Basic Streamlit dashboard (frontend — still basic as of Phase 8, see Section 6)
- Synthetic result: 200 events, 68.89% simulated recovery rate, INR 244,276 simulated
  recovered revenue. 17 tests passing.

### Phase 2 — ML Recovery Scoring & Priority Intelligence (BACKEND)
- Recovery Probability model: Logistic Regression, output is a probability, NOT a direct
  decision — threshold/business rules are kept separate from the raw score
- Features: failure category, payment method, previous successes/failures, customer age,
  subscription value, retry count, time/weekday
- Leakage protection: recovered/recovery_time/final_state explicitly excluded from features;
  train/test split is customer-group-based (zero customer overlap between splits)
- Artifacts: recovery_model.joblib + recovery_model_metadata.json (version, seed, feature
  list, excluded fields, metrics, class balance, error analysis, coefficients)
- Churn risk: a documented HEURISTIC, explicitly NOT a trained model
- revenue_at_risk = subscription_value * assumed_remaining_months
- Priority score combines recovery probability + churn risk + revenue-at-risk
- Measured (synthetic): 2,195 train / 805 test rows. Precision 0.7329, Recall 0.7488,
  F1 0.7407, ROC-AUC 0.7985. 23 tests passing.

### Phase 3 — Retry Timing & Payment Method Optimization (BACKEND)
- Recommends WHEN to retry from each customer's successful-payment-hour history
- Recommends WHICH method (CARD/UPI/NETBANKING/WALLET) from historical per-method success
- Cold-start customers get a safe documented fallback, not a guess dressed up as a
  prediction
- Every recommendation includes confidence, sample size, reason, and fallback indication
- Endpoint: POST /recommendations
- Synthetic result: baseline recovery 38.75% vs optimized 61.25%, revenue delta INR 28,482.
  29 tests passing.

### Phase 4 — Guardrails & Deterministic Decision Engine (BACKEND, safety-critical)
- 7 possible actions: RETRY_NOW, RETRY_LATER, CHANGE_PAYMENT_METHOD, SEND_NOTIFICATION,
  SUPPRESS_RETRY, ESCALATE_TO_HUMAN, STOP_RECOVERY
- 5 major guardrails: fraud hard stop, retry cap, high-value escalation, contact cooldown,
  gateway-incident suppression — plus idempotency
- Flow: Model signals + rules -> Guardrails -> Deterministic Decision Engine -> one approved
  action. NO LLM involvement at this step. Fully reproducible/testable/auditable.
- 

### Phase 5 — Bounded LLM Communication & AI Revenue Analyst (BACKEND, LLM boundary)
- LLM can: write a customer message for an ALREADY-approved action; answer business
  questions via 4 READ-ONLY tools: get_recovery_metrics, get_failure_breakdown,
  get_gateway_health, get_top_priority_cases
- LLM cannot: decide/trigger retries, stop payments, change amounts, bypass guardrails,
  override the decision engine, approve/reject/execute transactions
- Endpoints: POST /communication, POST /analyst
- Implementation is provider-neutral/offline-capable — runs without an external LLM API key
- 42 tests passing, including explicit LLM-boundary, guardrail-bypass, and
  tool-failure-disclosure tests

### Phase 6 — Experimentation & What-If Evaluation (BACKEND)
- Deterministic hash-based control/treatment assignment; recovery-rate and revenue
  comparison; 95% confidence interval; statistical-significance flag; what-if projection
- Endpoint: POST /experiments
- Synthetic result (500 events): control 48.08% / INR 126,750 vs treatment 61.25% /
  INR 144,750. Delta +13.17pp (95% CI 4.43-21.91pp), +INR 18,000 revenue, what-if
  projected 62.0%.
- Real bug hit and fixed: nested-dataclass JSON serialization failure, fixed via recursive
  dataclasses.asdict conversion — documented in the engineering log.
- 46 tests passing.

### Phase 7 — Offline Policy Learning (BACKEND, advanced/optional-scope item, already done)
- Contextual-bandit-style OFFLINE learner — explicitly NOT live/self-modifying
- Aggregates reward observations by category/action, selects highest-average-reward action
  offline, safe fallback for unseen context, offline comparison against the deterministic
  baseline
- Cannot bypass guardrails or the fraud hard stop; no live deployment, no automatic
  retraining, no financial authority
- Synthetic result: learned avg reward 0.9333 vs deterministic baseline 0.6667. Verified
  that a fraud case still resolves to STOP_RECOVERY even after a high-reward observation.
- 49 tests passing.

### Phase 8 — Docker, CI, Monitoring & Drift (INFRASTRUCTURE)
- Docker: Dockerfile, .dockerignore, docker-compose.yml. API on 8000, Streamlit dashboard on
  8501, SQLite named volume, environment-based DB path
- GitHub Actions CI: Python 3.12 -> deps -> pytest -> model-training check -> experiment
  script, triggered on push and PR
- Operational metrics: request count, error count, error rate, average latency, model
  version exposed. Endpoint: GET /operational-metrics
- Drift detection via Population Stability Index (PSI): <0.10 STABLE, 0.10-0.2499
  MODERATE_DRIFT, >=0.25 SIGNIFICANT_DRIFT. Endpoint: POST /drift. Monitoring signal only —
  does not silently change any financial decision or retry policy.
- Final validation: 53 tests passing total, plus Docker build/container-import checks,
  secret scan, .env-ignore check, GitHub remote/upstream checks.
- KNOWN ISSUE (not yet fixed): a scikit-learn version-mismatch warning when loading the
  saved model inside Docker. It runs, but dependency versions should be pinned (or the model
  retrained inside the container's exact environment) — this is real, outstanding technical
  debt, not a hypothetical risk.

## 4. Repository Structure (current)

AGENTS.md <- existing Codex development rules
README.md
docs/
blueprint.md <- original specification
roadmap.md <- official roadmap
architecture.md
what-broke.md <- real bugs + lessons, keep this updated going forward
phase-notes/ <- one file per phase
src/revenue_recovery/
api.py <- FastAPI endpoints
models.py <- data/domain models
database.py <- SQLite persistence
service.py <- core orchestration
synthetic.py <- synthetic events/outcomes
classification.py <- failure classification
scoring.py <- recovery/risk/priority scoring
optimization.py <- timing + payment-method recommendations
anomaly.py <- gateway/bank anomaly detection
guardrails.py <- safety constraints
decision_engine.py <- final deterministic action
llm_boundary.py <- bounded LLM behavior
experimentation.py <- control/treatment experiments
policy_learning.py <- offline policy learning
baseline.py <- fixed baseline for comparison
training.py <- model training
monitoring.py <- operational metrics + drift
tests/ <- 53 tests across all phases
scripts/ <- train_recovery_model.py, run_synthetic_batch.py,
run_experiment.py, evaluate_optimization.py,
evaluate_policy.py
dashboard/app.py <- current Streamlit frontend (BASIC — see Section 6)
models/ <- trained recovery model + metadata


Mental rule already established in this codebase: frontend presents, backend owns business
logic; ML produces a signal, the decision engine owns the financial action. Keep this
separation intact in every new phase.

## 5. Capability Snapshot

| Component | Status |
|---|---|
| FastAPI backend | Available, 11 endpoints |
| Frontend | Streamlit, basic reporting dashboard ONLY |
| Database | SQLite |
| Recovery model | Logistic Regression |
| Failure categories | 9 |
| Deterministic actions | 7 |
| AI Analyst tools | 4, read-only |
| Guardrails | 5 major + idempotency |
| Automated tests | 53, all passing as of Phase 8 |
| Docker / Compose | Available |
| CI (GitHub Actions) | Available |
| Monitoring / drift | Available (PSI) |

## 6. What Is Intentionally NOT Built Yet — This Is Your Actual Task List

**Frontend gap (the biggest one — call this out explicitly, don't bury it):** the only
frontend is a basic Streamlit reporting dashboard. There is no human-review queue UI, no
browsable/searchable audit-log UI, no proper case drill-down experience, no AI Revenue
Analyst chat interface, and no auth-aware views. This needs a real production frontend
(React/Next.js is the natural choice given the backend is a clean FastAPI/JSON API already).

**Backend/infra gaps, explicitly out of scope until now:**
- Real payment processing: no real Razorpay (or other gateway) credentials, no real
  bank/customer transactions, no webhook signature verification, no real
  notification/action providers (everything today is simulated)
- No authentication/authorization, no multi-tenancy, no rate limiting, no HTTPS enforcement
- SQLite, not PostgreSQL — no migrations framework yet
- No background task queue (Celery/RQ) — everything runs in-process/synchronous today
- No backups, no stronger observability beyond the basic operational metrics, no privacy/PII
  controls
- No Kubernetes, no Kafka/event streaming, no live/autonomous RL, no multi-agent
  architecture, no vector DB/RAG — these were deliberately excluded as premature and should
  only be added if an actual, articulated need arises, not by default
- The Docker scikit-learn version-mismatch warning (Section 3, Phase 8) is unresolved

## 7. Your Task

Take this from a tested, demo-ready prototype to a production-ready system, backend and
frontend both. Work in phases, continuing the existing numbering (Phase 9 onward), and
follow the same discipline already established: each phase should be fully working and
tested before you start the next one, with its own phase-notes entry.

**Step 0 — before writing any new code:** run the existing test suite, confirm all 53 tests
still pass, and sanity-check the real repository against Section 3/4/5 above. Flag any
discrepancy you find before proceeding.

**Suggested phase sequence for the remaining work (adjust if you find a better order, but
tell me why):**
- Phase 9 — Real payment gateway integration: Razorpay test-mode first, real webhooks with
  signature verification, credential handling via environment variables (ask me for actual
  keys when you reach this point — never invent or hardcode them)
- Phase 10 — Data layer hardening: PostgreSQL migration with a proper migrations tool,
  background task processing for retries/notifications instead of in-process scheduling
- Phase 11 — Auth, authorization, multi-tenancy: user auth, role-based access (who can view
  vs. who can resolve an ESCALATE_TO_HUMAN case), rate limiting, HTTPS
- Phase 12 — Production frontend: React/Next.js replacing/extending the Streamlit MVP —
  business dashboard, case drill-down with the audit trail exposed, a human-review queue,
  a browsable audit-log UI, an AI Revenue Analyst chat UI, and an experiments/what-if view,
  all auth-aware
- Phase 13 — Observability, security, and compliance hardening: structured logging, backups,
  secrets management, PII/privacy controls, and fixing the Phase 8 scikit-learn version
  mismatch
- Phase 14 — Scale-readiness, evaluated on actual need rather than by default: only
  introduce Kafka/event-bus, horizontal scaling, or a formal scheduled-retraining pipeline
  with human sign-off if real usage patterns actually justify it — don't add these
  speculatively

## 8. Working Agreement

- If you need information you don't have — real credentials, a business decision (e.g. exact
  escalation thresholds, which cloud provider, auth provider choice), or anything ambiguous
  about scope — ASK ME DIRECTLY. Don't guess or silently pick a default for anything
  security- or money-relevant.
- Commit at every meaningful checkpoint (mirror the existing one-commit-per-phase-milestone
  pattern already in this repo's history) with clear, conventional messages, and push to the
  GitHub remote regularly — don't let work sit uncommitted locally.
- Keep the repo clean and professional: update README.md and docs/architecture.md as the
  system changes, keep docs/what-broke.md current with real issues you hit (like the
  existing nested-dataclass and scikit-learn-version entries), and add a phase-notes file for
  each new phase, same as Phases 0-8.
- Never remove or weaken an existing passing test to make new code pass. Add new tests for
  new functionality, especially anything safety-related (auth bypass attempts, payment
  signature verification, guardrail preservation under the new frontend/API surface).
- Preserve every invariant in Section 2 through every phase below, no exceptions.