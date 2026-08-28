# What Broke — Development Log

This document records real problems encountered during development of the AI Revenue Recovery & Payment Intelligence Platform.

## Purpose

The log preserves useful engineering history, including bugs, failed implementations, incorrect assumptions, architectural problems, data leakage, test failures, integration failures, model issues, LLM boundary failures, security issues, dead ends, performance problems, and important lessons.

Do not fabricate problems. Record an issue only when it actually occurs and provides a meaningful lesson or requires a non-trivial response.

## Instructions

1. Assign the next sequential issue number.
2. Identify the phase and date.
3. Record observed evidence rather than speculation.
4. Describe the smallest reliable reproduction when applicable.
5. Separate root cause from symptoms.
6. Describe the actual fix and the checks proving it worked.
7. Do not remove unresolved issues merely because they are inconvenient.
8. Use `WONT_FIX` or `DEFERRED` honestly when appropriate.

## Issue Template

```markdown
## Issue #[NUMBER] — [SHORT TITLE]

### Phase

Phase X — [Phase Name]

### Date

YYYY-MM-DD

### Status

OPEN / FIXED / WONT_FIX / DEFERRED

### Severity

LOW / MEDIUM / HIGH / CRITICAL

### 1. Problem

What were we trying to do, and what went wrong?

### 2. Expected Behavior

What should have happened?

### 3. Actual Behavior

What actually happened? Include relevant errors, output, failed tests, or incorrect predictions.

### 4. Reproduction

List the smallest reliable steps required to reproduce the problem.

### 5. Root Cause

Why did the problem occur?

### 6. Fix

What was changed, or why was the issue deferred?

### 7. Verification

Which tests or checks proved the result?

### 8. Lesson

What should future development learn from this issue?
```

## Issue Log

## Issue #1 — Small Incident Window Caused a False Positive

### Phase

Phase 4 — System Intelligence and Guardrails

### Date

2026-08-27

### Status

FIXED

### Severity

MEDIUM

### 1. Problem

The incident test classified one failure among ten events as an active systemic incident.

### 2. Expected Behavior

A small sample should not trigger gateway-wide retry suppression.

### 3. Actual Behavior

The observed 10% rate exceeded three times the 2% baseline and activated the incident rule.

### 4. Reproduction

Evaluate gateway health with one failure, ten total events, a 2% baseline, and a 3x multiplier.

### 5. Root Cause

The default minimum evidence window was only ten events, allowing normal small-sample variation to dominate the multiplier.

### 6. Fix

The minimum default incident window was increased to twenty events.

### 7. Verification

The false-positive test and incident activation/recovery tests pass within the 37-test suite.

### 8. Lesson

Rate multipliers need a minimum sample requirement; relative thresholds alone are unsafe on sparse traffic.

## Issue #2 — Nested Experiment Dataclasses Failed JSON Serialization

### Phase

Phase 6 — Experimentation Engine

### Date

2026-08-27

### Status

FIXED

### Severity

LOW

### 1. Problem

The experiment report script failed after the test suite passed.

### 2. Expected Behavior

The script should print the experiment and what-if report as JSON.

### 3. Actual Behavior

`json.dumps` raised `TypeError: Object of type VariantMetrics is not JSON serializable`.

### 4. Reproduction

Run `python scripts/run_experiment.py` with an `ExperimentResult` containing nested dataclasses.

### 5. Root Cause

Using `result.__dict__` converted only the outer dataclass. Nested `VariantMetrics` objects remained custom Python objects.

### 6. Fix

Use `dataclasses.asdict` for recursive dataclass conversion in both the report script and typed API boundary.

### 7. Verification

The script now prints valid JSON, the typed experiment endpoint validates nested response models, and the full test suite passes.

### 8. Lesson

Unit tests for calculation logic do not replace running user-facing scripts; nested serialization requires an end-to-end check.

## Issue #3 — Attempt Budget Is Fixed at Enqueue Time, Not by Worker Config

### Phase

Phase 11 — Production Persistence & Durable Background Execution

### Date

2026-08-28

### Status

FIXED

### Severity

LOW

### 1. Problem

A test built a worker with `TaskQueue(max_attempts=2)` and a deliberately failing retry provider, expecting the task to reach `FAILED` after two cycles.

### 2. Expected Behavior

Two failed attempts against a queue configured for two attempts should exhaust the task.

### 3. Actual Behavior

The task was still `PENDING` after the second cycle.

### 4. Reproduction

Enqueue a task through a `TaskQueue(max_attempts=3)`, then process it with a worker holding `TaskQueue(max_attempts=2)` and a provider that raises.

### 5. Root Cause

`TaskQueue.max_attempts` is only used when writing a row. `mark_failed` compares `task.attempts` against `task.max_attempts`, which `_to_task` reads back from the row. The task had been enqueued by the service's own queue with the default budget of 3, so the worker's lower setting had no effect on it.

### 6. Fix

The test was corrected to run three cycles and assert `attempts == 3`, rather than changing the code. Reading the budget from the row is the behaviour we want: lowering `TASK_MAX_ATTEMPTS` in configuration must not retroactively cause the system to give up on already-approved actions that are still in flight.

### 7. Verification

`tests/test_worker.py::test_provider_failure_keeps_the_task_visible_and_retries_it` passes and asserts the row ends `FAILED` with `attempts == 3` while the outcome stays unrecovered.

### 8. Lesson

For durable work, per-row limits and process configuration are different things. A queued row should carry its own budget so a config change cannot alter the fate of work already accepted — but that means a test cannot shorten an existing task's budget by reconfiguring the worker.

## Issue #4 — Foreign Key Enforcement Blocked a Test That Fabricated a Broken Row

### Phase

Phase 11 — Production Persistence & Durable Background Execution

### Date

2026-08-28

### Status

FIXED

### Severity

LOW

### 1. Problem

A test needed to prove the worker refuses a task pointing at a non-existent event. It tried to repoint the task's `event_id`, disabling foreign keys first.

### 2. Expected Behavior

`PRAGMA foreign_keys = OFF` followed by the update would produce an orphaned task row.

### 3. Actual Behavior

`sqlalchemy.exc.IntegrityError: (sqlite3.IntegrityError) FOREIGN KEY constraint failed` on the update.

### 4. Reproduction

Inside a transaction on a SQLite connection with `foreign_keys=ON`, execute `PRAGMA foreign_keys = OFF` and then an update that violates a foreign key.

### 5. Root Cause

SQLite ignores `PRAGMA foreign_keys` inside a transaction, and the project's connections are opened with `engine.begin()`, so every statement runs in one. The pragma was silently a no-op and the constraint — enabled deliberately in this phase — did its job.

### 6. Fix

The test stopped fabricating a broken row in the database. It claims a real task, builds an orphan with `dataclasses.replace(task, event_id=999999)`, and asserts `RecoveryWorker._load_context` raises `LookupError`.

### 7. Verification

`tests/test_worker.py::test_a_task_pointing_at_a_missing_event_is_refused` passes, and the provider-failure test separately covers the worker's exception path end to end.

### 8. Lesson

Turning on referential integrity means the database will also refuse the invalid states a test wants to create. Fabricate the invalid input at the object boundary instead of trying to defeat the constraint.

## Issue #5 — Escalated Cases Were Never Scored, So No Reviewer Approval Could Ever Retry

### Phase

Phase 12 — Authentication, Roles, Tenant Isolation & Human Review

### Date

2026-08-28

### Status

FIXED

### Severity

HIGH

### 1. Problem

A new test signed in as an operator, took a high-value case out of the review queue, and resolved it as `MANUAL_RETRY`. The retry was supposed to be re-decided by the deterministic engine and, for a customer the model rates highly, executed.

### 2. Expected Behavior

`ResolveCaseResponse.executed is True` for a case the engine approves, and `False` only when the engine withholds it.

### 3. Actual Behavior

`assert False is True`. Every resolution was withheld, no matter whose case it was or what the customer's history looked like.

### 4. Reproduction

Ingest an event whose amount is above `high_value_threshold` (default 50000), so the `HIGH_VALUE_REVIEW` guardrail escalates it. Read `GET /review-queue`: `recovery_probability` is `null`. Resolve it with `MANUAL_RETRY`: the engine returns `STOP_RECOVERY`.

### 5. Root Cause

`RecoveryService.process_event` skipped ML scoring whenever *any* guardrail blocked the event — a reasonable-looking optimisation, since a fraud decline or a capped retry gains nothing from a probability. But a high-value escalation is not finished; it is waiting for a person. With no `scores` row, `_load_case` coalesced `recovery_probability` to `0.0`, and the re-decision compared `0.0` against the retry threshold of `0.40` and stopped recovery. Two things followed: the review queue could never produce a retry, and its priority ordering — which is derived from the same score — was meaningless, so the queue was sorted by nothing.

### 6. Fix

Scoring now covers the one blocking rule that is an escalation rather than an ending. `evaluate_guardrails`' rule names became module constants, and `process_event` computes `should_score = preliminary_guardrail.allowed or preliminary_guardrail.rule == HIGH_VALUE_REVIEW`. Fraud declines and capped retries are still unscored: nothing downstream reads their probability, and scoring a case nobody may act on would only invite someone to act on it.

### 7. Verification

`tests/test_service.py::test_an_escalated_case_carries_the_models_view` asserts an escalated case has a probability and a priority score and that the queue exposes the same value; `test_a_stopped_case_is_not_scored` pins that fraud and capped cases stay unscored. End to end, a loyal high-value customer scored 0.7669 and the approved retry executed and recorded `RECOVERED`; a risky one scored 0.0130, the retry was withheld, the case stayed `ESCALATED`, and `recovered_events` stayed 0. `tests/test_api_auth.py` covers both outcomes through the API.

### 8. Lesson

A guardrail that blocks is not necessarily a guardrail that ends. `HIGH_VALUE_REVIEW` exists to hand the case to a human, and a human needs the same evidence the automation would have used — so an "escalate" outcome has to keep everything a later decision depends on. Also: a `COALESCE(..., 0.0)` in a read path turned a missing score into a confident "almost certainly unrecoverable", which is how a data gap became a silent policy.

## Issue #6 — An Expired Session Looked Like a Backend Outage

### Phase

Phase 12 — Authentication, Roles, Tenant Isolation & Human Review

### Date

2026-08-28

### Status

FIXED

### Severity

MEDIUM

### 1. Problem

The dashboard's HTTP client was taught to distinguish "your session is gone" (401) from every other failure, so the UI could re-prompt for a password instead of reporting an error. A test asserting that a token-less call raises `AuthenticationRequiredError` failed.

### 2. Expected Behavior

`APIClient.get_metrics()` with no token raises `AuthenticationRequiredError`.

### 3. Actual Behavior

`APIClientError: Unexpected error calling /metrics: Client error '401 Unauthorized' for url ...` — the generic fallback, not the specific class.

### 4. Reproduction

Route the client's `requests.request` at a FastAPI `TestClient` and call any protected endpoint without a token.

### 5. Root Cause

The client classified errors by exception type, via `response.raise_for_status()` inside `except requests.exceptions.HTTPError`. FastAPI's `TestClient` is httpx-based, so it raised `httpx.HTTPStatusError`, which that clause does not catch, and the 401 fell through to the catch-all. The same fragility would appear in production behind any layer that returns a non-`requests` response object.

### 6. Fix

`_request` no longer calls `raise_for_status()`. It branches on `response.status_code >= 400` and maps 401 to `AuthenticationRequiredError` and everything else to `APIClientError`. The status code is the actual contract with the backend; which library raised is an implementation detail. In the dashboard, a `SessionAPIClient` subclass catches `AuthenticationRequiredError` once, drops the token, and reruns the script on the login form — so no individual panel has to remember to handle it.

### 7. Verification

`tests/test_api_client.py::test_api_client_reports_missing_token_as_authentication_required` passes, and `test_api_client_reports_forbidden_role_as_plain_error` asserts a 403 is *not* an `AuthenticationRequiredError`: a permission the account genuinely lacks must not send the user back to the login form to try the same password again.

### 8. Lesson

Classify HTTP failures by status code, not by the exception type the transport happens to raise. Tests that swap the transport (httpx for requests) will find this immediately, which is a reason to route the client through the real app in tests rather than a hand-written mock.



