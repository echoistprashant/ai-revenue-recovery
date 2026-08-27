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
