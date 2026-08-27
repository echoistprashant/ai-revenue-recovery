# AI Revenue Recovery & Payment Intelligence Platform
### Full Phased Build Roadmap — Portfolio-Grade Version

This is the complete vision, broken into 8 independent phases. There's no deadline pressure
here, so the rule changes from "cut aggressively" to "build in an order where every phase
leaves you with something fully working." You should never be sitting on a pile of
half-finished, non-functional code — each phase is a complete, demoable milestone on its own.

**How to use this:** Don't start a phase until the previous phase's Definition of Done is
fully checked off. Each phase is independently portfolio-worthy — if you ever stop, you stop
with something complete, not something broken. (One tactical note: if you ever want to submit
a slice of this to the Razorpay Buildathon along the way, Phases 1+2 together already make a
strong, complete submission on their own — the two goals aren't mutually exclusive.)

---

## Roadmap at a Glance

| Phase | Name | Core Question It Answers | Builds On | Rough Effort |
|---|---|---|---|---|
| 1 | Core Payment Recovery | Can we detect, classify, and retry failed payments end-to-end? | — | 1–2 weeks |
| 2 | Machine Learning Layer | Can we predict which payments are recoverable, and how much they're worth? | Phase 1 | 1–2 weeks |
| 3 | Recovery Optimization | Can we choose the best time and method, not just retry blindly? | Phase 2 | 1 week |
| 4 | System Intelligence & Guardrails | Is the system safe, bounded, and aware of systemic issues? | Phase 1–3 | 1 week |
| 5 | GenAI Layer | Can an LLM add real value without ever making a financial decision? | Phase 1–4 | 1–2 weeks |
| 6 | Experimentation Engine | Can we prove which strategy actually performs better? | Phase 1–5 | 1 week |
| 7 | Advanced AI (optional) | Can the system learn its own policy over time? | Phase 1–6 | 2+ weeks |
| 8 | Production Engineering | Would this survive real infrastructure and real operations? | All above | 1–2 weeks |

Total: roughly 2–3 months at a steady part-time pace. Skip Phase 7 entirely and you lose
nothing essential — it's marked optional for a reason, and plenty of strong portfolio
projects stop at Phase 6 or even Phase 4.

---

## Phase 1 — Core Payment Recovery (the Foundation)

**Goal:** A working end-to-end system with zero ML and zero LLM — pure solid engineering.
Everything after this is additive intelligence layered on a system that already runs.

**Build:**
- Event ingestion (webhook receiver + a synthetic event generator) that normalizes different
  "gateway formats" into one common internal schema
- Rule-based failure classification into: `INSUFFICIENT_FUNDS, EXPIRED_CARD, INVALID_CARD,
  AUTHENTICATION_FAILURE, BANK_DECLINED, GATEWAY_OR_NETWORK_FAILURE, FRAUD_RISK_DECLINE,
  PAYMENT_METHOD_FAILURE, TEMPORARY_BANK_ISSUE`
- Fixed-interval rule-based retry (e.g. retry after 1hr, 6hr, 24hr) — deliberately dumb;
  this becomes your baseline for every later comparison
- Outcome tracking (did the retry succeed?)
- Idempotency (`payment_id + attempt_id` as a unique key) — build this now, it's much harder
  to retrofit once other phases depend on the ingestion layer
- Basic audit log (every decision + timestamp + one-line reason) — also build this now, not
  in Phase 8. Every later phase gets easier to debug once this exists.
- A minimal dashboard: total failures, recovery rate, failure breakdown by category

**New tech:** Python, FastAPI, Pydantic, SQLite (or Postgres from the start if you prefer),
APScheduler for timing

**Data model (used by every phase from here on):**
`payment_id, customer_id, subscription_id, amount, currency, payment_method, gateway, bank,
failure_code, failure_category, timestamp, hour, day_of_week, previous_success_count,
previous_failure_count, customer_age_days, subscription_value, retry_count, retry_delay,
recovered, recovery_time, churned`

**Definition of Done:**
- [ ] A synthetic batch flows through ingestion → classification → fixed-interval retry →
      outcome tracking automatically, no manual steps
- [ ] Duplicate events never create duplicate retries
- [ ] Every decision has a timestamp and a one-line reason in the audit log
- [ ] Dashboard shows real, non-zero recovery-rate numbers
- [ ] This "dumb baseline" recovery rate is recorded somewhere — you'll compare every future
      phase against it, so don't lose this number

---

## Phase 2 — Machine Learning Layer

**Goal:** Replace guessing with prediction. This is where the project becomes a genuine ML
project, not a rules engine with a dashboard bolted on.

**Build:**
- **Recovery Probability Model** — the centerpiece. Binary classifier predicting
  P(this payment eventually recovers). Ship Logistic Regression as your baseline, then train
  XGBoost or LightGBM and compare against it.
- **Customer Behavioral Profiling** — aggregate per-customer features (recovery rate,
  preferred payment method, most successful payment hours, average amount) that feed the
  model above
- **Churn Prediction Model** — a second binary classifier: will this customer churn if this
  payment isn't recovered? Build this as a real trained model now — but be honest in your
  write-up about how much genuine signal your synthetic data contains; don't oversell a model
  trained on data you generated yourself
- **Revenue-at-Risk** — `subscription_value × expected_remaining_lifetime`
- **Priority Score** — `recovery_probability × churn_probability × revenue_at_risk`, so the
  system can answer "which failure matters most," not only "which failure happened"

**New tech:** pandas, numpy, scikit-learn, xgboost/lightgbm, matplotlib/seaborn for evaluation

**Definition of Done:**
- [ ] Recovery model evaluated on a held-out split with precision, recall, F1, and ROC-AUC
      reported — not just accuracy
- [ ] Churn model evaluated the same way, with the same honesty about weak spots
- [ ] Dashboard now shows a ranked priority list, not a flat list of failures
- [ ] You can show a measured recovery-rate improvement over the Phase 1 baseline

---

## Phase 3 — Recovery Optimization

**Goal:** Stop treating every recovery action as generic — choose the best time and the best
method per payment.

**Build:**
- **Intelligent Retry Timing** — predict each customer's best retry window from their
  historical successful-payment times (hour of day, day of week) instead of a fixed interval.
  This needs your Phase 1 synthetic generator enriched with believable per-customer
  time-of-day patterns — worth revisiting it now.
- **Next-Best-Payment-Method Recommendation** — given a customer's success history across
  UPI/Card/NetBanking, recommend whichever is most likely to succeed next. A ranked lookup
  against historical per-method success rate is legitimate here — you don't need a
  heavyweight recommender system for this to be real.
- **Dynamic Retry Strategy** — the decision engine now chooses action + timing + method
  together, instead of each being decided in isolation

**Definition of Done:**
- [ ] Retry-timing predictions are measurably different across different customers, not one
      fixed window applied to everyone
- [ ] Payment-method recommendations come with a confidence/success-rate number attached
- [ ] Recovery rate improves again over the Phase 2 number — measure and record it

---

## Phase 4 — System Intelligence & Guardrails

**Goal:** Make the system safe to run autonomously, and aware of problems bigger than any
single payment.

**Build:**
- **Risk & Fraud Guardrails** — `FRAUD_RISK_DECLINE` is a hard stop, checked before any model
  or LLM involvement, with no config path that overrides it
- **Human-in-the-Loop Threshold** — transactions above a configurable value always escalate
  to a human, regardless of what any model predicts
- **Bank/Gateway Anomaly Detection** — monitor rolling failure rates per bank/gateway; detect
  when failures spike well above baseline — a systemic incident, not an individual payment
  problem
- **Intelligent Retry Suppression** — when an incident is detected, automatically pause
  retries routed through the affected bank/gateway until it recovers, instead of hammering an
  already-struggling system
- **Centralized Decision Engine** — everything from Phases 1–4 converges here into one
  function outputting exactly one of: `RETRY_NOW, RETRY_LATER, CHANGE_PAYMENT_METHOD,
  SEND_NOTIFICATION, SUPPRESS_RETRY, ESCALATE_TO_HUMAN, STOP_RECOVERY`

**Definition of Done:**
- [ ] A test proves a fraud-flagged payment is never auto-retried, under any configuration
- [ ] A test proves a high-value payment always escalates to a human
- [ ] Injecting a simulated bank outage into your data visibly triggers suppression, and
      visibly resumes once the outage clears
- [ ] The decision engine is the only place actions come from — no other module decides
      anything on its own

---

## Phase 5 — GenAI Layer

**Goal:** Add an LLM exactly where it adds real value — never where it makes a financial
decision.

**Build:**
- **Dynamic Customer Communication** — the decision engine approves an action first; the LLM's
  only job is writing the message text for that already-approved action.
  `Decision Engine → Approved Action → LLM → Message`. It should be structurally impossible
  for the LLM to choose the action itself.
- **Explainable AI** — add SHAP to your tree-based models so a specific prediction can be
  broken down into positive/negative contributing factors, in plain English
- **AI Revenue Analyst** — a tool-calling chat layer. A business user asks a question in plain
  English ("why did recovery fall yesterday?", "which bank is causing the most failures?");
  the LLM calls real functions (`get_recovery_metrics()`, `get_failure_breakdown()`,
  `get_revenue_at_risk()`, `get_gateway_health()`) and answers using only what those functions
  actually return
- **Root Cause Analysis** — really just another question the Revenue Analyst answers via the
  same tool-calling pattern, not a separate system to build

**Definition of Done:**
- [ ] You can point at the code and show the LLM literally cannot execute a retry or change
      an amount
- [ ] Every prediction on the dashboard has a plain-English "why" a non-technical person
      could read and understand
- [ ] The Revenue Analyst correctly answers at least 5 different real business questions,
      sourced entirely from live tool calls, with zero invented numbers

---

## Phase 6 — Experimentation Engine

**Goal:** Move from "we think this works better" to "we proved this works better."

**Build:**
- **A/B Testing** — run two recovery strategies (e.g. retry-after-2-hours vs.
  retry-after-8-hours) against comparable customer segments; measure recovery rate, revenue,
  and churn for each
- **What-If Simulation** — let a business user ask "what if we retried after 6 hours instead
  of 24?" and get a projected outcome from your model, without touching production behavior
- **Recovery Strategy Comparison** — a clean report format: strategy vs. strategy, with a
  clear winner and the metrics that justify it

**Definition of Done:**
- [ ] Two strategies run against the same synthetic population produce statistically
      distinguishable results
- [ ] The what-if simulator's projection and a real A/B test's actual result land in the same
      ballpark when checked against each other — a good sanity check your simulation logic
      isn't just making up plausible-looking numbers

---

## Phase 7 — Advanced AI (Optional / Stretch)

**Goal:** Let the system learn its own recovery policy over time instead of you hand-designing
it. This is genuinely advanced — a complete, impressive portfolio project can stop before this
phase, and that's a perfectly reasonable place to stop.

**Build (if you choose to):**
- Frame recovery as a sequential decision problem: state = customer/payment/failure/risk
  context, actions = `{retry now, retry later, change method, send reminder, stop, escalate}`,
  rewards = positive for recovered/retained, negative for unnecessary retries, complaints,
  fraud exposure, or churn
- Start with contextual bandits before attempting full reinforcement learning — much simpler,
  and usually the right level of complexity for this problem anyway
- Only attempt this once Phase 2's supervised model is genuinely solid — RL layered on a weak
  baseline just learns to be confidently wrong, faster

**Definition of Done (if attempted):**
- [ ] The learned policy is compared against your Phase 2–4 hand-designed policy on the same
      evaluation set, with a clear, honest before/after number — including if the learned
      policy doesn't actually beat the hand-designed one, which is a real and useful finding

---

## Phase 8 — Production Engineering

**Goal:** Prove this could survive real infrastructure and real operations, not just a
synthetic batch on your laptop.

**Build:**
- **Event-driven architecture** — swap simple ingestion for a real event bus (Kafka or
  Redpanda) so the system handles continuous, high-volume traffic rather than one static batch
- **Async processing** — Redis + Celery for background job handling (retries, notifications)
  instead of in-process scheduling
- **Containerization & CI/CD** — Docker for reproducible environments, GitHub Actions for
  automated testing on every commit
- **Model Monitoring** — track precision/recall/F1/calibration over time in production-like
  conditions, with alerting if performance drops
- **Data & Model Drift Detection** — monitor whether incoming data (e.g. payment-method mix)
  has shifted meaningfully from what your models were trained on
- **Model Registry** — MLflow to version and track every model trained across all phases
- **Observability** — Prometheus + Grafana dashboards for system health, alongside your
  business dashboard

**Definition of Done:**
- [ ] The whole pipeline runs in Docker with one command
- [ ] CI runs your test suite automatically on every push
- [ ] A simulated data-drift scenario (e.g. shifting the payment-method mix) is actually
      detected and flagged, not just theoretically monitored
- [ ] A Grafana dashboard shows system health alongside your business metrics dashboard

---

## Repo Structure (grows with you, phase by phase)

```
ai-revenue-recovery/
  README.md
  docs/
    architecture.md
    what-broke.md          <- keep this running from Phase 1 onward
    phase-notes/            <- one short file per phase: what you built, what you learned
  data/
    generate_synthetic.py
  src/
    ingestion/              <- Phase 1
    classification/         <- Phase 1
    scoring/                <- Phase 2 (recovery model, churn model, revenue-at-risk, priority)
    optimization/           <- Phase 3 (retry timing, next-best-method)
    guardrails/              <- Phase 4
    decision_engine/         <- Phase 4
    communication/           <- Phase 5 (bounded LLM messaging)
    analyst/                 <- Phase 5 (AI Revenue Analyst)
    experimentation/         <- Phase 6
    policy_learning/         <- Phase 7 (optional)
  dashboard/
  tests/
  models/                    <- saved model artifacts, versioned by phase
  notebooks/                 <- exploration and evaluation notebooks
  docker/                    <- Phase 8
  .github/workflows/         <- Phase 8
  requirements.txt
  .env.example
```

---

## Closing Notes

- **Every phase should leave you with something that runs.** If you're deep into a phase with
  nothing demoable yet, that's a signal to descope that phase, not to push through blindly —
  the same principle that mattered for the hackathon version still applies, just stretched
  over months instead of days.
- **Write a short note per phase** as you finish it — what you built, what surprised you, what
  broke. By Phase 8 this becomes a genuinely compelling development history, and it's worth
  more to anyone reviewing your work than the final code alone.
- **Phases 1–2 alone are already a strong, complete project.** Everything past that is depth,
  not a requirement — don't let the full 8-phase roadmap make you feel like anything short of
  Phase 8 is unfinished.
