# Phase 14 — Security, Observability, and Data Protection

## Objective

Close the gap between "the guardrails are correct" and "this can be operated safely":
make the two boot-critical secrets fail loudly, stop a captured webhook from being
replayable forever, take customer identifiers out of the log stream, and make the model
artifact and its runtime agree. No new infrastructure.

## Why this was needed

Phase 12 made `JWT_SECRET_KEY` fail loudly in production and left
`RAZORPAY_WEBHOOK_SECRET` defaulting to `test_webhook_secret` — a value published in
`.env.example`, in the README, and in the test suite. Anyone holding it can post a
signed `payment.failed` event and drive a real retry.

Separately, an HMAC signature proves a payload came from someone holding the secret. It
does not prove *when*. One captured delivery stayed valid indefinitely.

And the log stream carried raw `payment_id` and `customer_id` values, plus — in one
line — the PostgreSQL password.

## Implemented

### The webhook secret fails at boot, not in traffic (`security.py`, `config.py`)

`resolve_webhook_secret(settings)` mirrors the existing `resolve_signing_key` shape.
Outside production it returns the configured value untouched, so development and the test
suite keep using the simulation secret. In production it raises
`InsecureWebhookSecretError` when the value is empty or is still
`test_webhook_secret` — "is still the published example value". `create_app` calls it
next to the token signer, so both secrets that can authorise a write are resolved at
startup: an operator sees a failed boot instead of finding a 401 in live traffic.

A short-but-genuine secret is warned about and accepted. Razorpay lets the operator
choose the secret, so refusing on length would block a correct deployment; that is a
different judgement from `JWT_SECRET_KEY`, whose length this project controls.

`Settings.uses_default_webhook_secret` exposes the predicate so nothing has to re-derive
the comparison.

### Webhook replay protection (`webhook_security.py`)

Razorpay sends **no timestamp header** — unlike Stripe, whose `Stripe-Signature` carries
a `t=` element, there is nothing to check outside the body. What it does send is a
`created_at` epoch second at the top level of the event, and that field is *inside the
signed bytes*: editing it invalidates the signature. So the timestamp is trustworthy to
exactly the degree the signature is.

`delivery_timestamp(payload)` reads the event's own `created_at`, falls back to the
payment entity's, and returns `None` rather than guessing — "no timestamp" is a different
fact from "timestamp of now". It skips `bool` explicitly, because `True` is an `int` in
Python and would date a delivery to 1970 and reject it for the wrong reason.

`check_freshness(...)` compares against the local clock with a symmetric window,
default 300s, configurable via `WEBHOOK_TOLERANCE_SECONDS` and rejected at construction
if non-positive. A delivery from the future is refused as firmly as a stale one: a sender
whose clock runs ahead would otherwise widen the replay window by however far it runs.

Freshness is checked **after** the signature, because a timestamp is only worth trusting
once it is known to be inside signed bytes.

`require_timestamp` is on in production only. A genuine Razorpay delivery always carries
`created_at`, so an undated payload in production is either not from Razorpay or has been
stripped to defeat this check. Development leaves it off so the simulation scripts and
the hand-built payloads already in the suite — which predate this check and are replays
of nothing — keep working. This is the reason no existing test needed changing.

### Freshness is not the guard that protects money

Idempotency is. The two do different jobs and fail differently:

- **Freshness** rejects a delivery too old to be a live gateway callback.
- **Idempotency** on `(tenant_id, payment_id, attempt_id)` means a *fresh* duplicate —
  a genuine Razorpay retry, or a replay inside the window — returns the first stored
  decision without re-running the pipeline or executing an action again.

This was proved rather than asserted. `CountingRetryProvider` records every outbound
retry; two byte-identical, validly signed, in-window deliveries produce
`provider.attempts == ["pay_replay_1"]`, and the second response carries
`duplicate: true` with the first `event_id`. A second test confirms a genuinely new
`attempt_id` is *not* treated as a replay, so the deduplication cannot swallow a real
second attempt.

### Structured logging and identifier masking (`observability.py`)

`JsonFormatter` emits one JSON object per line: timestamp, level, logger, message, then
whatever the call site attached through `extra=`. Exceptions are reduced to `error_type`
and `error_message` — no traceback, because frame text can quote input the record should
not carry.

`mask_identifier()` gives a gateway identifier a readable four-character prefix and a
truncated SHA-256 of the whole value: `pay_***138504fc6bc7`. Deterministic, so two lines
about the same payment still join, while the line no longer carries the value needed to
look that customer up in the Razorpay dashboard. The docstring is explicit that this is
masking, not anonymisation: an attacker holding candidate identifiers can hash and match.
It removes the realistic exposure for a log file, which is copy-and-paste.

`redact()` blanks any key named after a secret, over every emitted record. Defence in
depth — no call site passes one, and if one ever does it still does not reach the sink.

`safe_database_url()` strips a URL's userinfo password. The worker's startup line logged
`self.database.url` directly, which wrote the PostgreSQL password into every log sink on
every start. That is now fixed.

`safe_error_text(exc)` scrubs a third-party exception message before it is *stored*.
Two real shapes motivated it: a SQLAlchemy connection error quotes the URL it dialled, and
Google's Generative Language REST API takes its key as `?key=`. Both would land in
`tasks.last_error`, which operators read, and in the analyst's tool-failure reply. Driver-
interpolated parameter values are deliberately kept: they are the identifiers already in
that tenant's own `payment_events` row, so removing them would cost the diagnosis and
disclose nothing new.

`configure_logging()` is a no-op unless `LOG_FORMAT=json`, and production defaults to
json without an operator having to remember the variable.

### Observability, without a new stack

No new monitoring dependency. The existing operational-metrics and PSI drift surfaces
already answer "is the system healthy" and "has the input distribution moved"; the gap
was that individual log lines were unstructured and unfilterable, which is a formatter
problem, not a platform problem. What was added is context on lines that already existed:
`task_type`, `attempts`, `error_type`, and `max_attempts` on worker failures; `reason`,
`body_bytes`, and `skew_seconds` on each webhook rejection path, so the four ways a
delivery can be refused are distinguishable in a query rather than by reading prose.

### scikit-learn version mismatch: pinned, not retrained

Docker warned `InconsistentVersionWarning` on every model load. The committed artifact
was trained with scikit-learn 1.9.0; `pyproject.toml` pinned `>=1.7,<1.8`.

**Decision: pin the dependency to `>=1.9,<1.10`.** Retraining in-container was the
alternative and was rejected: `models/recovery_model_metadata.json` publishes the metrics,
the class balance, the error analysis, and the ten largest coefficients *of one specific
artifact*. Rebuilding the model at image-build time would mean those published numbers
stop describing what actually runs, and the image would no longer be reproducible from
the repository alone. The pin makes the runtime match the artifact that the documented
numbers describe.

The pin alone would be a comment that rots, so the invariant is now enforced:

- `training.py` records `sklearn_version` in **both** the joblib artifact and the
  metadata JSON.
- `RecoveryScorer` compares the recorded version against the runtime and logs a
  structured warning naming the artifact path, both versions, and the remedy. It still
  loads: refusing would take the service down over what is usually a stale image, and the
  deterministic guardrails sit between any score and any action.
- Four tests tie the three together — the artifact records a version, the runtime matches
  it, the `pyproject.toml` specifier admits it, and the metadata names the same one. A
  future dependency bump without a retrain is a failed test, not a warning in a log.

The model was retrained to add the field. Diffing the metadata confirms the only change
is the new key: identical metrics (`precision 0.7329`, `recall 0.7488`, `f1 0.7407`,
`roc_auc 0.7985`), identical error analysis, identical coefficients. The seeded pipeline
is reproducible.

### Data protection inventory (`docs/data-protection.md`)

Written by reading `schema.py` and every logging call site rather than from intent. It
lists every column that relates to a person, states what is deliberately absent (no name,
email, phone, address, card number, last-four, expiry, CVV, token, mandate reference, IP,
or user-agent — the platform reads the gateway's *decision*, never the instrument), and
explains why identifiers stay unmasked in the database while being masked in logs: the
database is the asset the access controls guard, and `(tenant_id, payment_id, attempt_id)`
is the idempotency key that stops a customer being charged twice.

It also records the retention stance — 24 months for financial records and the audit
trail, 90 days for completed tasks, 30 days for log sinks — and says plainly that **none
of it is enforced in code**: there is no scheduled deletion job, no `DELETE FROM` on an age
predicate anywhere in the repository, no `retention_days` setting, and no data-subject
request endpoint. What it does record is why the future work is tractable: every table
carries `created_at`, and the foreign keys run one way from `payment_events`, so a safe
deletion order is derivable rather than guessed.

## Guardrail invariants preserved

- **Fraud hard stop has no override path.** Nothing in this phase touches the decision
  engine, the guardrail order, or any role's capabilities.
- **Every action still routes through the same engine.** Both new refusals — an insecure
  secret at boot, a stale delivery at the route — reject the request *before*
  `process_event` is reached. Neither creates a new path to an action; they only remove
  paths.
- **Guardrails still sit between scoring and execution.** Scoring and execution are
  unchanged. The scorer's new mismatch warning is a log line, not a decision.
- **No existing test was weakened or deleted.** The undated-payload allowance in
  development is the design choice that made that possible.

## Verification

Full backend suite from a clean checkout:

```text
294 passed
```

That is 246 at the end of Phase 13 plus 48 new: 18 in `tests/test_webhook_security.py`,
18 in `tests/test_observability.py`, 5 appended to `tests/test_security.py`, 6 appended to
`tests/test_scoring.py`, and 1 appended to `tests/test_worker.py`. No existing test file
lost a test or had an assertion relaxed.

What the new tests pin, chosen for the cases where a mistake would be silent:

- **`tests/test_webhook_security.py`** — timestamp extraction including the `True`-is-an-int
  trap; the symmetric window and its inclusive boundary (300s accepted, 301s not); an
  hour-old capture with a *still-valid signature* refused; an undated delivery refused in
  production and allowed in development; a malformed body answered with exactly
  `"Malformed Razorpay webhook payload"` and never echoing itself; a byte-identical replay
  reaching the gateway exactly once; a new `attempt_id` not swallowed as a replay; and the
  production app refusing to boot with the published secret.
- **`tests/test_observability.py`** — masking is stable, differs per identifier, and leaves
  `None`/empty alone; a database URL loses its password; `redact` touches only
  secret-named keys, including one passed through `extra=`; an exception is reduced to type
  and message with no traceback anywhere in the payload; `configure_logging` is a no-op for
  every value but `json`; `safe_error_text` removes a connection-string password and a
  `?key=` value while keeping the host, the endpoint, and driver-interpolated identifiers.
- **`tests/test_scoring.py`** — the artifact/runtime/pin/metadata agreement described above,
  plus a mismatched artifact still loading while logging both versions, and an older
  artifact with no recorded version not being treated as a mismatch.
- **`tests/test_worker.py`** — a provider failure that quotes credentials leaves none of
  them in the stored `tasks.last_error`, while the type, host, and endpoint survive.

Each new guard was checked by breaking it. The clearest case: reverting
`disable_existing_loggers=False` in `migrations/env.py` makes
`test_a_programmatic_migration_leaves_existing_loggers_enabled` fail, then restoring it
makes it pass. A test that has never failed has not been shown to test anything.

## Issues found and fixed

Four real defects surfaced while building this phase. Three of them were pre-existing.

- **The PostgreSQL password was written into every log sink.** `worker.py` logged
  `self.database.url` on startup, and a PostgreSQL URL carries the password in its
  userinfo. Now routed through `safe_database_url()`. This was the most severe finding in
  the phase and it was found by grepping log call sites, not by a failing test.

- **A migration switched the application's logging off.** `migrations/env.py` called
  `logging.config.fileConfig(...)` with its default `disable_existing_loggers=True`, which
  marks every logger created before that point as disabled. Harmless for the Alembic CLI,
  which exits immediately; not harmless for anything that migrates in-process and then
  expects to keep logging — a deploy script, or a test session. It surfaced as two new
  `caplog` assertions passing alone and failing in the full suite, because
  `tests/test_migrations.py` runs alphabetically before them and silently disabled
  pytest's capture. Fixed with `disable_existing_loggers=False`, and pinned by a test that
  migrates and then asserts a pre-existing logger is still enabled.

- **`create_app` reconfigured the host's root logger.** The first version called
  `configure_logging()` inside the factory, which tears out and replaces every root
  handler. The factory is called dozens of times by the test suite and by the simulation
  scripts — including with production settings — so constructing an app destroyed the
  caller's logging. Moved to the two genuine process entry points: the module-level
  `app = create_app()` that `uvicorn revenue_recovery.api:app` loads, and
  `scripts/run_worker.py`, which falls back to the readable single-line format when JSON
  was not asked for, since it is also run by hand. `observability.py`'s own docstring had
  already stated this rule; the first implementation broke it.

- **A stored task error could carry credentials.** `tasks.last_error` held
  `f"{type(exc).__name__}: {exc}"` verbatim, and that column is read by operators. A
  SQLAlchemy connection failure quotes the URL it dialled; an HTTP failure against Google's
  Generative Language API quotes `?key=`. Both now go through `safe_error_text()`.

Also corrected during the phase: two epoch-to-UTC assertions in the new test file were
written from arithmetic rather than checked (`1772198400` is `13:20Z`, not `12:00Z`), and
`attempt_id` was being logged unmasked next to a masked `payment_id` — it is a Razorpay
identifier too.

## Scope & limitations

- **Freshness is checked against the local clock.** There is no NTP requirement in this
  repository. A server whose clock has drifted more than 300s will refuse genuine
  deliveries; the log line carries `skew_seconds`, which is what makes that diagnosable in
  one query rather than by guesswork.
- **Masking is not anonymisation.** Anyone holding a list of candidate identifiers can
  hash them and match. It removes the copy-and-paste path from a log line to a gateway
  dashboard, which is the realistic exposure for a log file, and nothing more.
- **Retention is documented, not enforced.** Stated explicitly in
  `docs/data-protection.md` §5 and repeated here so it is not mistaken for a shipped
  feature. No deletion job exists.
- **No replay protection is possible against a `created_at`-less gateway.** This works
  because Razorpay puts a timestamp inside the signed bytes. A gateway that signs no
  timestamp at all cannot be defended this way, and idempotency would be the only guard.
- **The real Razorpay webhook path is still unverified against live traffic.** Everything
  here was tested with locally signed payloads, which is a weaker claim: they exercise the
  code's understanding of the format, not Razorpay's actual bytes. The live test-mode
  delivery belongs to the Razorpay integration block that follows this phase.
  "Configured it" is not the same claim as "watched a real webhook get processed
  correctly", and only the second one will be recorded as done.
- **The full stack signed-in end to end was not exercised here either.**
  `docs/phase-notes/phase-13.md` deferred that check to "Phase 14's manual verification".
  This phase did not do it: nothing in it touched the frontend, and inventing a browser
  session run would be worse than carrying the gap forward. It is still open, and it is
  listed as open rather than quietly dropped.
- **Log-sink retention, encryption at rest, and data-subject endpoints are out of scope**
  and named as such in the data-protection document.
