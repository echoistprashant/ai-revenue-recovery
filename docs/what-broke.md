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



## Issue #7 — The Worker Wrote the PostgreSQL Password Into Every Log Sink

### Phase

Phase 14 — Security, Observability, and Data Protection

### Date

2026-08-30

### Status

FIXED

### Severity

HIGH

### 1. Problem

Phase 14 began with a review of every logging call site, looking for customer identifiers. It found something worse than an identifier.

### 2. Expected Behavior

A startup log line names the database the worker connected to, so an operator can confirm it is the intended one. It should not carry the credential used to reach it.

### 3. Actual Behavior

`worker.py` logged `extra={"database": self.database.url}`. For any deployment with `DATABASE_URL` set, that URL is `postgresql+psycopg://revenue:<password>@host:5432/db`, and the password went to stdout on every worker start — into the container log, into whatever shipper collects it, and into every retained copy.

### 4. Reproduction

Set `DATABASE_URL=postgresql+psycopg://revenue:s3cr3t-pw@localhost:5432/revenue_recovery`, start `python scripts/run_worker.py`, and read the first log line.

### 5. Root Cause

A SQLAlchemy URL is a single string that happens to contain a credential. `self.database.url` reads like a harmless connection descriptor at the call site, and it is one on SQLite, which is what development uses — so the line looked correct throughout every phase where it was written and reviewed. The dual-driver work in Phase 11 changed what that string contains without changing the line that logs it.

### 6. Fix

`observability.safe_database_url()` splits the URL, replaces the userinfo password with `<redacted>`, and keeps the scheme, user, host, port, and database name, which are the operationally useful parts. The worker's startup line now passes through it. A SQLite URL, having no userinfo, is returned unchanged.

Defence in depth was added rather than relying on this one fix: `JsonFormatter` now passes every emitted record through `redact()`, which blanks the value of any key named after a secret. A future call site that logs a raw credential under a key like `password` or `token` still does not reach the sink.

### 7. Verification

`tests/test_observability.py::test_a_database_url_is_logged_without_its_password` asserts the password is gone and the host and database name survive; `test_a_sqlite_url_is_left_alone` asserts the development path is unchanged. `test_the_formatter_redacts_a_secret_passed_through_extra` covers the second layer.

### 8. Lesson

Grep the log call sites, do not reason about them. This line was read during code review in three separate phases and looked right every time, because on the driver those reviews were running it *was* right. A value that is safe to log under one configuration is not therefore safe to log — and the review that catches it is the one that asks what the string contains in production, not what it contains locally.

## Issue #8 — A Migration Silently Disabled the Application's Loggers

### Phase

Phase 14 — Security, Observability, and Data Protection

### Date

2026-08-30

### Status

FIXED

### Severity

MEDIUM

### 1. Problem

Two new tests asserting on log output passed when run alone and failed when run in the full suite. `caplog.text` was empty.

### 2. Expected Behavior

`caplog` captures a `logging.warning(...)` emitted during a test, regardless of what earlier tests in the session did.

### 3. Actual Behavior

```text
assert "shorter than recommended" in caplog.text
AssertionError: assert 'shorter than recommended' in ''
```

Failing for both `tests/test_security.py::test_a_short_webhook_secret_is_warned_about_but_accepted` and `tests/test_scoring.py::test_a_mismatched_artifact_warns_with_both_versions_and_still_loads`, while `python -m pytest tests/test_security.py` alone was green.

### 4. Reproduction

`python -m pytest tests/test_migrations.py tests/test_security.py::test_a_short_webhook_secret_is_warned_about_but_accepted` fails. Either file alone passes. Bisecting file-by-file against the failing test is what identified `tests/test_migrations.py`.

### 5. Root Cause

`migrations/env.py` calls `logging.config.fileConfig(config.config_file_name)`. That function's `disable_existing_loggers` parameter defaults to `True`, which sets `.disabled = True` on every logger that already existed. `tests/test_migrations.py` drives Alembic in-process via `alembic.command.upgrade`, so from that point in the session onward, `revenue_recovery.*` loggers emitted nothing.

The first suspect was wrong. `configure_logging()` also replaces root handlers, and a production `create_app(...)` in the new webhook tests calls it — so that was fixed first (see below) and the failure persisted, which is what pointed at Alembic.

### 6. Fix

`fileConfig(config.config_file_name, disable_existing_loggers=False)`, with a comment explaining that the default is only safe for the CLI, which exits.

The unrelated defect found while chasing this one was fixed separately; see Issue #9.

### 7. Verification

The full suite is green at 294 passed. `tests/test_observability.py::test_a_programmatic_migration_leaves_existing_loggers_enabled` runs a migration and asserts a logger created beforehand is still enabled; reverting `disable_existing_loggers=False` makes it fail, and restoring it makes it pass, so the guard is known to test something.

### 8. Lesson

A test that fails only in a suite is reporting global state, and logging is global state that three separate libraries feel entitled to own. Two lessons, and the second is the one that generalises: when a fix does not clear the failure, the fix was for a different bug — keep it if it stands on its own merit, but stop treating it as the explanation. Both changes here were correct; only one was the cause.

## Issue #9 — Constructing an Application Object Tore Out the Caller's Logging

### Phase

Phase 14 — Security, Observability, and Data Protection

### Date

2026-08-30

### Status

FIXED

### Severity

MEDIUM

### 1. Problem

The first version of the structured-logging work called `configure_logging()` from inside `create_app()`, which is the wrong place by a rule the module's own docstring already stated.

### 2. Expected Behavior

`create_app(service, settings=...)` builds and returns a FastAPI application. It is a factory: the test suite calls it dozens of times, the simulation scripts call it, and the webhook tests call it with production settings. Calling it should have no effect outside the object it returns.

### 3. Actual Behavior

`configure_logging()` removes every existing root handler before installing its own — deliberately, so a deployment gets one JSON line per record instead of that line plus uvicorn's plain-text copy. Called from a factory, that meant any `create_app(...)` with `LOG_FORMAT=json` or production settings silently detached pytest's `caplog` handler and any handler the host process had configured, for the remainder of the process.

### 4. Reproduction

Construct an app with production settings, then assert on a log record emitted afterwards:

```python
create_app(service, settings=Settings(environment="production", ...), signing_key="k" * 40)
logging.getLogger("revenue_recovery.x").warning("visible?")   # not captured
```

### 5. Root Cause

Root-logger configuration is process-wide state, and a factory is not a process. `observability.py`'s docstring says the module is called from entry points only; the first implementation put the call in the most convenient place — the one function every entry point already goes through — which is exactly the wrong shape, because non-entry-points go through it too.

### 6. Fix

Moved to the two genuine process entry points:

- `src/revenue_recovery/api.py` module tail, next to `app = create_app()`. That module object is what `uvicorn revenue_recovery.api:app` loads, so it is the API's entry point.
- `scripts/run_worker.py`, which falls back to the readable single-line `basicConfig` format when JSON was not asked for, since it is also run by hand.

`create_app()` retains only `resolve_webhook_secret(...)`, which validates configuration and mutates nothing global.

### 7. Verification

`tests/test_observability.py::test_configure_logging_does_nothing_unless_json_was_asked_for` and `test_configure_logging_installs_the_json_handler_when_asked` pin the function's own contract, the latter restoring the original handlers in a `finally` block so it does not commit the same sin it tests for. The two `caplog` assertions that motivated the investigation now pass in the full suite.

### 8. Lesson

This one was written down before it was violated — the docstring stated the rule, and the first implementation broke it anyway. A convention only holds if something enforces it, and the enforceable version of "only entry points configure logging" is that the function lives nowhere a non-entry-point would naturally call it.

## Issue #10 — A Stored Task Error Could Carry the Credentials It Quoted

### Phase

Phase 14 — Security, Observability, and Data Protection

### Date

2026-08-30

### Status

FIXED

### Severity

MEDIUM

### 1. Problem

`tasks.last_error` stored `f"{type(exc).__name__}: {exc}"` verbatim, and that column is read by operators in the frontend. The same verbatim text was returned to the analyst chat when a read-only tool failed.

### 2. Expected Behavior

A stored error names what failed and where, so an operator can diagnose a stuck task without reading the container logs.

### 3. Actual Behavior

Third-party exception messages were not written with a durable store in mind, and two shapes in this project's own dependency set quote a credential:

- A SQLAlchemy connection failure quotes the URL it dialled — `postgresql+psycopg://revenue:<password>@host:5432/db`.
- An HTTP failure against Google's Generative Language API quotes the request URL, and that API takes its key as `?key=<api key>`.

Either one lands in a database column and on an operator's screen.

### 4. Reproduction

Inject a retry provider that raises `RuntimeError("connect to postgresql+psycopg://revenue:s3cr3t-pw@db.internal:5432/recovery failed via https://api.example.com/charge?key=AIzaSyREAL")`, run the worker over the queued task, and read `tasks.last_error`.

### 5. Root Cause

The exception message was treated as diagnostic text, which it is, and not as attacker-supplied-or-credential-bearing content, which it also is. Nothing in the codebase had previously stored a third-party message durably; Phase 11's durable queue introduced the column that made it persistent, and the LLM boundary's tool-failure path made it operator-visible.

### 6. Fix

`observability.safe_error_text(exc, limit=...)` formats the exception, substitutes a URL userinfo password and any secret-named query parameter with `<redacted>`, and truncates to fit the column. Applied at both sinks: `worker.py`'s `mark_failed(...)` call, and `llm_boundary.py`'s tool-failure reply.

Parameter values a driver interpolated into a failing statement — `UNIQUE constraint failed: payment_events.payment_id [pay_abc]` — are deliberately kept. They are identifiers already stored in that same tenant's own row, so removing them would cost the diagnosis and disclose nothing new.

### 7. Verification

`tests/test_worker.py::test_a_stored_task_error_does_not_keep_the_credentials_it_quoted` drives a real failure through the queue and asserts neither secret survives in `tasks.last_error` while `RuntimeError`, the host, and the endpoint path all do. Six tests in `tests/test_observability.py` pin the scrubber itself, including that a word merely ending in `key` (`monkey=banana`) is not treated as a credential and that driver-interpolated identifiers are kept.

### 8. Lesson

A regex-based scrubber only knows the shapes it was told about, so this is mitigation and not a guarantee. The finding that generalises is about the boundary rather than the pattern: the moment an exception message stops being written to a stream nobody keeps and starts being written to a column somebody reads, it becomes content that needs a policy. That transition happened in Phase 11 and the policy arrived three phases later.

## Issue #11 — Environment Variable Key Mismatch for Webhook Signing Secret

### Phase

Phase 15 — Block 3 Real Razorpay Integration

### Date

2026-08-30

### Status

FIXED

### Severity

MEDIUM

### 1. Problem

The `.env` file contained `WEBHOOK_SECRET_KEY = "Prashant@2817"`, but `config.py` read `RAZORPAY_WEBHOOK_SECRET`. The application booted using default test fallback values instead of loading the user-provided secret.

### 2. Expected Behavior

The application settings should read the webhook signing secret from `RAZORPAY_WEBHOOK_SECRET` as defined in `.env.example` and `config.py`.

### 3. Actual Behavior

`RAZORPAY_WEBHOOK_SECRET` fell back to `DEFAULT_WEBHOOK_SECRET` ("test_webhook_secret"), leading to signature verification failures when webhooks signed with the real key arrived.

### 4. Root Cause

Variable name mismatch in `.env`.

### 5. Fix

Updated `.env` key to `RAZORPAY_WEBHOOK_SECRET` and updated `config.py` to support explicit Razorpay credentials loading (`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`).

### 6. Verification

`tests/test_razorpay_live.py::test_real_webhook_payload_ingestion_end_to_end` passes and verifies signature verification with `RAZORPAY_WEBHOOK_SECRET`.

### 7. Lesson

Maintain explicit alignment between `.env`, `.env.example`, and `config.py` parameter keys.


## Issue #12 — Webhook Freshness Check Rejected Static Test Timestamp Epochs

### Phase

Phase 15 — Block 3 Real Razorpay Integration

### Date

2026-08-30

### Status

FIXED

### Severity

LOW

### 1. Problem

A newly written live integration test for webhook payload processing failed with HTTP 401 `Razorpay webhook delivery refused as a possible replay. Delivery timestamp ... sits ... seconds from current UTC clock`.

### 2. Expected Behavior

The simulated payload should pass freshness checks and be ingested into the payment recovery service.

### 3. Actual Behavior

The test payload used a static hardcoded epoch timestamp (`1772198400`), which differed by more than `WEBHOOK_TOLERANCE_SECONDS` (300 seconds) from the current UTC clock.

### 4. Root Cause

Phase 14 security added timestamp freshness validation against current UTC time. Static test timestamps outside the 300s symmetric window are correctly rejected as replays.

### 5. Fix

Updated test suite to dynamically generate `created_at` timestamps using `int(datetime.now(timezone.utc).timestamp())`.

### 6. Verification

`tests/test_razorpay_live.py::test_real_webhook_payload_ingestion_end_to_end` passes with dynamic fresh timestamps.

### 7. Lesson

Tests targeting security components enforcing time freshness must supply dynamic timestamps anchored to `now()` or mock the clock fixture explicitly.

