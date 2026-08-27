# AGENTS.md

# AI Revenue Recovery & Payment Intelligence Platform

This repository contains the implementation of the
AI Revenue Recovery & Payment Intelligence Platform.

The purpose of this project is to build a resume-grade,
interview-defensible AI Engineering system for intelligent
recurring-payment recovery.

---

# 1. SOURCE OF TRUTH

The following documents define the project:

1. `docs/blueprint.md`
2. `docs/roadmap.md`
3. `docs/what-broke.md`

### Priority

If there is any uncertainty:

1. Follow the explicit project blueprint.
2. Follow the current roadmap phase.
3. Preserve the existing architecture.
4. Prefer the simplest solution that satisfies the requirements.
5. Ask for clarification before making a major architectural change.

Do NOT silently change the project scope.

Do NOT introduce new technologies simply because they are popular
or because they could make the project appear more "production-grade."

---

# 2. PROJECT OBJECTIVE

Build an AI-powered Revenue Recovery system that can:

Payment Event
    ↓
Ingestion
    ↓
Failure Classification
    ↓
Recovery Probability
    ↓
Churn Risk
    ↓
Revenue at Risk
    ↓
Priority Score
    ↓
Guardrails
    ↓
Deterministic Decision Engine
    ↓
Action
    ↓
Outcome
    ↓
Audit / Feedback
    ↓
Analytics / AI Revenue Analyst

The system must demonstrate the complete loop:

PREDICT → DECIDE → ACT → MEASURE → LEARN

---

# 3. DEVELOPMENT PHILOSOPHY

This is a learning-oriented AI Engineering project.

The goal is NOT merely to produce working code.

The implementation must be understandable, explainable,
testable, maintainable, and defensible in a technical interview.

Prefer:

- simple architecture
- readable code
- explicit logic
- strong validation
- meaningful tests
- documented assumptions
- measurable results

Avoid:

- unnecessary abstractions
- unnecessary frameworks
- unnecessary microservices
- unnecessary dependencies
- premature optimization
- speculative features
- artificial complexity

---

# 4. PHASE-BASED DEVELOPMENT

The project is divided into multiple phases.

Work on ONE phase at a time.

Never silently start a future phase.

Before implementing a phase:

1. Inspect the current repository.
2. Read the relevant section of `docs/blueprint.md`.
3. Read the relevant section of `docs/roadmap.md`.
4. Inspect existing implementation.
5. Identify dependencies on previous phases.
6. Create a short implementation plan.
7. Identify files that will be created or modified.
8. Define acceptance criteria.
9. Define tests/checks required for completion.

Only then implement the phase.

---

# 5. PLAN BEFORE IMPLEMENTATION

Unless explicitly instructed otherwise, do NOT immediately modify
the repository when starting a new phase.

First provide:

## Objective

What this phase is supposed to accomplish.

## Existing State

What already exists and can be reused.

## Implementation Plan

The exact steps that will be taken.

## Files

Files that will be created, modified, or deleted.

## Dependencies

Libraries, modules, APIs, or previous phases required.

## Acceptance Criteria

How we will determine that the phase is complete.

## Tests

What must be tested.

## Risks

Potential implementation or integration problems.

Wait for approval when the task requires architectural
changes or when the requirements are ambiguous.

---

# 6. IMPLEMENT ONLY THE REQUESTED SCOPE

When instructed to implement a phase:

- implement only that phase
- preserve existing interfaces where possible
- do not rewrite unrelated code
- do not refactor unrelated modules
- do not introduce future-phase functionality
- do not modify working behavior without justification

If implementation requires a change outside the current phase:

1. explain why
2. identify affected files
3. explain the risk
4. ask for approval if the change is architectural or substantial

---

# 7. ARCHITECTURE

The primary architecture is:

Payment Gateway / Simulator
        ↓
Event Ingestion
        ↓
Failure Classification
        ↓
ML / Scoring
        ↓
Guardrails
        ↓
Deterministic Decision Engine
        ↓
Action Executor
        ↓
Audit / Outcome
        ↓
Dashboard / Analytics
        ↓
AI Revenue Analyst

The architecture must remain modular.

The following responsibilities should remain separate:

- ingestion
- classification
- feature engineering
- prediction
- risk calculation
- guardrails
- decision making
- action execution
- audit logging
- analytics
- LLM interaction

Do not combine unrelated responsibilities into one large module.

---

# 8. CRITICAL LLM BOUNDARY

The LLM is NOT the financial decision maker.

This is a non-negotiable architectural rule.

The LLM MUST NOT:

- decide whether a payment should be retried
- decide whether a payment should be stopped
- trigger a payment retry
- change a payment amount
- change financial parameters
- bypass a guardrail
- override the deterministic decision engine
- approve a transaction
- reject a transaction
- independently execute payment actions

The deterministic decision engine is responsible for financial
and recovery actions.

The LLM may ONLY:

1. Generate customer-facing communication for an already-approved
   action.

2. Answer analytics questions using approved tools and real
   project data.

The flow must remain:

Models + Rules
    ↓
Decision Engine
    ↓
Approved Action
    ↓
LLM
    ↓
Customer Communication

NOT:

LLM
    ↓
Financial Decision

---

# 9. CORE GUARDRAILS

Guardrails must be evaluated BEFORE automated recovery actions.

The system must support:

## Fraud Hard Stop

If:

`failure_category == FRAUD_RISK_DECLINE`

then:

`STOP_RECOVERY`

No automatic retry.

The LLM cannot override this.

---

## High-Value Escalation

If the transaction exceeds the configured human-review threshold:

`ESCALATE_TO_HUMAN`

The threshold must be configurable.

Do not hard-code business assumptions throughout the codebase.

---

## Retry Cap

If the maximum retry count has been reached:

`STOP_RECOVERY`

The system must never continue retrying indefinitely.

---

## Contact Frequency Cap

Do not repeatedly contact the same customer within the configured
cooldown period.

---

## Idempotency

Duplicate payment events must not create duplicate actions.

For duplicate:

`payment_id + attempt_id`

the system should process the event only once.

---

# 10. DECISION ENGINE

The decision engine must be deterministic and testable.

Possible actions include:

- `RETRY_NOW`
- `RETRY_LATER`
- `CHANGE_PAYMENT_METHOD`
- `SEND_NOTIFICATION`
- `SUPPRESS_RETRY`
- `ESCALATE_TO_HUMAN`
- `STOP_RECOVERY`

The decision engine may consume:

- failure category
- recovery probability
- churn risk
- revenue at risk
- priority score
- retry count
- fraud status
- transaction amount
- gateway health
- recommended payment method

The LLM must NOT be responsible for selecting these actions.

---

# 11. MACHINE LEARNING RULES

ML components must be treated as engineering components,
not black boxes.

For every ML model:

1. Define the prediction target.
2. Define available features.
3. Prevent data leakage.
4. Create a baseline.
5. Train the model.
6. Evaluate the model.
7. Perform error analysis.
8. Document assumptions.
9. Save/version the model artifact where appropriate.
10. Integrate it through a stable prediction interface.

Never fabricate model performance.

Never invent accuracy, recovery rate, revenue recovery,
or other business metrics.

Only report measurements produced by actual experiments.

---

# 12. RECOVERY MODEL

The baseline recovery model should use Logistic Regression
unless the project blueprint explicitly changes this requirement.

The model should output a probability:

Example:

`0.87`

meaning an estimated 87% probability of recovery.

The implementation must distinguish between:

- probability
- classification
- decision threshold

Do not automatically assume:

`probability > 0.5`

is the correct business decision.

Business thresholds must be justified.

---

# 13. CHURN RISK

If the blueprint specifies a heuristic churn score,
keep it as a heuristic.

Do NOT present a heuristic as a trained ML model.

Clearly document:

- formula
- assumptions
- normalization
- limitations

Never fabricate churn-model performance metrics
for a heuristic.

---

# 14. REVENUE AT RISK

Revenue-at-risk calculations must use documented assumptions.

Do not present assumptions as observed facts.

For example:

`revenue_at_risk = subscription_value × assumed_remaining_months`

The remaining-month assumption must be configurable.

Document the business reasoning and limitations.

---

# 15. PRIORITY SCORING

Priority scoring should combine the approved project signals,
such as:

- recovery probability
- churn risk
- revenue at risk

The formula must remain documented and deterministic.

Do not silently change the formula because another approach
seems more sophisticated.

---

# 16. PAYMENT METHOD RECOMMENDATION

The next-best payment method should remain a simple,
explainable recommendation unless the project blueprint
explicitly introduces a more advanced recommender.

Use historical payment behavior where appropriate.

Handle cold-start cases with a documented fallback.

---

# 17. ANOMALY / INCIDENT DETECTION

Gateway/bank anomaly detection must remain separate from
individual payment recovery prediction.

The system should detect abnormal increases in failure rate
relative to an appropriate baseline.

When a significant incident is detected:

`INCIDENT_DETECTED`

may cause:

`SUPPRESS_RETRY`

for affected transactions.

Do not allow the LLM to determine whether a gateway incident exists.

---

# 18. DATA RULES

Synthetic data must be reproducible.

Always use explicit random seeds where appropriate.

Synthetic data should contain realistic relationships.

Avoid completely random features that have no relationship
with the target.

Examples of realistic relationships:

- insufficient funds may recover after a delay
- expired cards may require payment-method updates
- temporary gateway failures may recover later
- gateway outages may create correlated failures
- repeated payment failures may increase churn risk
- customer payment history may influence recovery probability

Do not leak target information into features.

Information only available AFTER the recovery decision
must not be used as an input to that decision.

---

# 19. DATA LEAKAGE

Treat data leakage as a critical ML defect.

Examples of potentially invalid features:

- recovery outcome
- future payment success
- post-recovery timestamp
- information generated after the decision

When in doubt:

Ask:

"Would this information actually be available at the moment
the recovery decision is being made?"

If not, it cannot be a prediction feature.

---

# 20. DATABASE RULES

Use the database defined by the project blueprint.

Keep schema design explicit.

Prefer:

- primary keys
- foreign keys
- unique constraints
- indexes where justified
- transactions where required

Do not add a database technology without justification.

Database logic should not be duplicated across many files.

---

# 21. API RULES

Use typed request and response schemas.

Validate inputs.

Return meaningful errors.

Do not expose internal stack traces to API users.

Keep business logic outside route handlers where practical.

Routes should orchestrate services rather than contain the
entire application.

---

# 22. EVENT PROCESSING

Payment events should follow:

Receive
    ↓
Validate
    ↓
Normalize
    ↓
Persist
    ↓
Process
    ↓
Decide
    ↓
Act
    ↓
Record Outcome

Events must be idempotent.

Duplicate events must not create duplicate financial actions.

---

# 23. PAYMENT SIMULATOR

The payment simulator is for development and demonstration.

It must NOT pretend to be a real banking/payment processor.

Use it to demonstrate:

- success
- failure
- retry
- delayed recovery
- gateway failure
- incident conditions

Never use real payment credentials in the repository.

---

# 24. RAZORPAY TEST MODE

If a Razorpay test-mode adapter is implemented:

- isolate it behind an adapter/interface
- keep synthetic simulation as the fallback
- never commit credentials
- never expose secrets
- do not make the application depend entirely on live external
  services

The core project must remain runnable without external
payment credentials.

---

# 25. LLM TOOL CALLING

The AI Revenue Analyst should use approved tools.

Tools should return real project data.

The LLM must not fabricate:

- revenue numbers
- recovery rates
- failure counts
- gateway health
- customer risk
- model metrics

If a tool fails:

- report the limitation
- do not invent a replacement value

Tool results should be clearly separated from generated prose.

---

# 26. LLM ANALYTICS TOOLS

Use the approved analytics tools from the blueprint.

Examples include:

- `get_recovery_metrics()`
- `get_failure_breakdown()`
- `get_gateway_health()`
- `get_top_priority_cases(n)`

Do not add many unnecessary tools.

Each tool must have:

- clear purpose
- typed inputs
- typed outputs
- error handling
- tests

---

# 27. AUDITABILITY

Important decisions must be auditable.

Where appropriate, record:

- event ID
- payment ID
- customer ID
- timestamp
- failure category
- recovery probability
- churn risk
- revenue at risk
- priority
- selected action
- guardrail result
- model version
- decision reason
- outcome

The audit trail must explain:

"What happened?"

"Why did the system choose this action?"

"What was the outcome?"

---

# 28. EXPLAINABILITY

Every automated recovery decision should have a human-readable
reason.

Example:

"RETRY_LATER was selected because recovery probability was high,
the transaction was below the escalation threshold, no active
gateway incident was detected, and the customer has historically
paid successfully during the recommended retry window."

Do not expose meaningless internal implementation details
as the only explanation.

---

# 29. TESTING

Tests are mandatory.

At minimum, test:

## Unit Tests

- failure classification
- recovery scoring
- churn calculation
- revenue-at-risk
- priority scoring
- guardrails
- decision engine
- payment-method recommendation
- anomaly detection

## Safety Tests

- fraud hard stop
- retry cap
- high-value escalation
- duplicate event idempotency
- LLM cannot bypass guardrails

## Integration Tests

Test the complete flow:

Payment Event
    ↓
Ingestion
    ↓
Classification
    ↓
Prediction
    ↓
Risk
    ↓
Guardrails
    ↓
Decision
    ↓
Action
    ↓
Audit
    ↓
Outcome

Never modify tests merely to make incorrect implementation pass.

If a test fails, investigate the implementation first.

---

# 30. BASELINE COMPARISON

The project must have a baseline.

The baseline should represent a simple fixed retry strategy.

Compare:

BASELINE
vs
AI RECOVERY SYSTEM

Measure actual results such as:

- recovery rate
- recovered revenue
- failed retries
- unnecessary retries
- suppressed retries
- unresolved cases

Do not fabricate improvement percentages.

---

# 31. EXCEPTION HANDLING

Do not hide failure cases.

Maintain an unresolved/exception list.

Every unresolved case should have:

- payment ID
- reason
- final state
- explanation

A system that honestly reports failures is preferable
to a system that artificially shows 100% success.

---

# 32. MONITORING

Where monitoring is implemented, track useful signals such as:

Application:

- request count
- error rate
- latency

Payment system:

- failed payments
- recovered payments
- recovery rate
- gateway failure rate

ML:

- prediction distribution
- model version
- basic data drift indicators where practical

Do not build complex MLOps infrastructure unless required.

---

# 33. SECURITY

Never commit:

- `.env`
- API keys
- access tokens
- passwords
- payment secrets
- private credentials
- authentication secrets

Use:

`.env.example`

for configuration documentation.

Before every commit:

1. inspect `git status`
2. inspect `git diff`
3. check for secrets
4. verify `.gitignore`

---

# 34. DEPENDENCY MANAGEMENT

Before adding a dependency:

1. Check whether the standard library or existing dependency
   can solve the problem.
2. Explain why the dependency is needed.
3. Add the smallest reasonable dependency.
4. Pin or constrain versions where appropriate.
5. Update dependency documentation if necessary.

Do not add libraries simply because they are popular.

---

# 35. CODE QUALITY

Prefer:

- meaningful names
- small functions
- single responsibility
- explicit types
- clear interfaces
- useful comments
- predictable error handling

Avoid:

- giant functions
- magic numbers
- duplicated business rules
- hidden global state
- unnecessary inheritance
- unnecessary abstraction layers

Business thresholds should be configurable.

---

# 36. DOCUMENTATION

Maintain documentation throughout development.

Important files include:

`README.md`

`docs/blueprint.md`

`docs/roadmap.md`

`docs/architecture.md`

`docs/what-broke.md`

Documentation should describe the implementation that actually
exists, not an imagined future implementation.

---

# 37. WHAT-BROKE DOCUMENTATION

`docs/what-broke.md` must contain real development issues.

For each meaningful issue document:

## Problem

What happened?

## Root Cause

Why did it happen?

## Fix

What was changed?

## Lesson

What was learned?

Do not invent bugs.

Do not hide important mistakes.

Examples of valuable entries:

- data leakage
- incorrect schema assumptions
- duplicate webhook bug
- model threshold problem
- anomaly detector false positive
- API integration failure
- LLM tool hallucination prevention
- database constraint issue

---

# 38. GIT WORKFLOW

Git is part of the engineering process.

Do NOT create one giant commit at the end.

Commit incrementally.

Recommended workflow:

PLAN
    ↓
IMPLEMENT
    ↓
TEST
    ↓
REVIEW
    ↓
DOCUMENT
    ↓
COMMIT
    ↓
PUSH
    ↓
NEXT PHASE

---

# 39. PHASE COMMIT REQUIREMENT

At the END of every completed phase:

1. Run relevant tests.
2. Fix legitimate failures.
3. Update documentation.
4. Update `docs/what-broke.md` if applicable.
5. Inspect `git status`.
6. Inspect `git diff`.
7. Check for secrets.
8. Run `git diff --check`.
9. Create a meaningful commit.
10. Push to the configured GitHub repository.
11. Verify the push succeeded.

A phase is NOT considered complete until the GitHub push
has successfully completed.

---

# 40. COMMIT MESSAGE FORMAT

Use:

`<type>(phase-X): <short description>`

Examples:

`feat(phase-03): add synthetic payment generator`

`feat(phase-08): add recovery probability model`

`feat(phase-15): add deterministic decision engine`

`feat(phase-18): add gateway anomaly detection`

`feat(phase-22): add AI revenue analyst`

`test(phase-26): add decision guardrail tests`

`docs(phase-30): complete project documentation`

Commit messages must accurately describe what was actually changed.

---

# 41. GITHUB PUSH FAILURE

If a push fails:

1. Do not claim success.
2. Read the actual Git error.
3. Diagnose the issue.
4. Fix it if possible.
5. Retry.
6. Verify the remote branch.
7. Only report success after the push succeeds.

Never fabricate a commit hash or GitHub status.

---

# 42. AFTER EVERY PHASE

Report:

## Phase

Which phase was completed.

## Changes

What was implemented.

## Tests

What tests/checks were run.

## Issues

What problems were encountered.

## Documentation

What documentation was updated.

## Git

Commit hash.

Commit message.

## GitHub

Whether push succeeded.

## Next

What the next phase will build.

Do not start the next phase automatically unless instructed.

---

# 43. DEBUGGING RULE

When something fails:

DO NOT immediately rewrite large parts of the project.

First:

1. reproduce the failure
2. inspect the error
3. identify the root cause
4. identify the smallest safe fix
5. implement the fix
6. run regression tests

Avoid speculative fixes.

Do not change unrelated components while debugging.

---

# 44. ARCHITECTURAL CHANGE RULE

If you believe the current architecture is insufficient:

STOP before making a major change.

Explain:

1. Current limitation.
2. Why it matters.
3. Proposed architecture change.
4. Files/components affected.
5. Benefits.
6. Costs.
7. Risks.
8. Simpler alternatives.

Do not silently redesign the project.

---

# 45. NO BUZZWORD ENGINEERING

Do not introduce:

- Kafka
- Kubernetes
- Celery
- complex agent frameworks
- reinforcement learning
- vector databases
- RAG
- multi-agent systems
- advanced MLOps platforms

unless explicitly required by the blueprint or explicitly
approved.

Technology must solve a real project problem.

---

# 46. DEFERRED FEATURES

The following are intentionally deferred unless explicitly approved:

- reinforcement learning
- full fraud detection platform
- complex RAG
- multi-agent architecture
- Kubernetes
- unnecessary microservices
- multi-cloud deployment
- advanced experimentation infrastructure
- unnecessary streaming infrastructure

Do not implement deferred features during earlier phases.

---

# 47. RESUME-GRADE QUALITY

The final project should demonstrate:

- real problem definition
- data engineering
- ML modeling
- model evaluation
- decision intelligence
- backend engineering
- database design
- event processing
- guardrails
- LLM tool calling
- testing
- observability
- documentation
- Git/GitHub discipline

The project should be defensible in an AI Engineering interview.

Never claim capabilities that the implementation does not actually
have.

---

# 48. LEARNING REQUIREMENT

This project is also a learning project.

When asked to explain an implementation, explain:

1. What was implemented.
2. Why it was implemented.
3. What concepts are involved.
4. What alternatives exist.
5. Why the chosen approach is appropriate.
6. What assumptions were made.
7. What can fail.
8. How it is tested.
9. How it could be improved.

Do not hide important implementation decisions behind abstractions.

---

# 49. STOP CONDITIONS

Stop and ask for clarification if:

- the blueprint conflicts with the requested implementation
- a major architecture change appears necessary
- a security-sensitive decision is unclear
- payment behavior is ambiguous
- requirements are contradictory
- an external credential is required but unavailable
- a proposed feature would materially increase project scope

Do not guess when guessing could change the system architecture
or financial behavior.

---

# 50. FINAL DEFINITION OF DONE

The project is complete only when:

- core payment flow works
- failure classification works
- recovery probability works
- churn risk works
- revenue-at-risk works
- priority scoring works
- guardrails work
- deterministic decision engine works
- action execution works
- anomaly detection works
- retry suppression works
- audit trail works
- outcome tracking works
- AI Revenue Analyst works through approved tools
- dashboard works
- critical tests pass
- baseline comparison is completed
- unresolved cases are documented
- documentation is complete
- Docker/reproducible setup works where required
- no secrets are committed
- Git history shows incremental development
- final changes are pushed to GitHub

Most importantly:

The implementation must satisfy the project's blueprint
without unnecessary complexity.

The goal is not to build the largest system.

The goal is to build a complete, measurable, explainable,
well-engineered AI Revenue Recovery system.