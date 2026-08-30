# Data Protection: What This System Stores, Logs, and Keeps

This is a factual inventory, written by reading the schema and every logging call site
rather than from intent. It records what personal data the platform holds, where it
goes, what was changed in Phase 14 to reduce it, and — stated plainly — what is
described here as a stance but is **not yet enforced in code**.

Nothing in this document is a compliance certification. It is the input a compliance
review would need.

## 1. What personal data exists at all

The complete set of columns in `src/revenue_recovery/schema.py` that relate to a person:

| Table | Column | What it is | Category |
| --- | --- | --- | --- |
| `payment_events` | `customer_id` | Razorpay's customer identifier | Pseudonymous identifier |
| `payment_events` | `subscription_id` | Razorpay's subscription identifier | Pseudonymous identifier |
| `payment_events` | `payment_id`, `attempt_id` | Razorpay's payment / attempt identifiers | Pseudonymous identifier |
| `payment_events` | `amount`, `currency`, `subscription_value` | What was charged | Financial |
| `payment_events` | `payment_method`, `bank` | `card` / `upi` / …, and the issuing bank name | Financial, low granularity |
| `payment_events` | `previous_success_count`, `previous_failure_count`, `customer_age_days`, `retry_count` | Behavioural counters | Derived, about a person |
| `payment_events` | `failure_code`, `failure_category` | Why the charge failed | Financial |
| `users` | `username` | An operator's login name | Staff identity |
| `users` | `password_hash` | bcrypt hash | Credential (not reversible) |
| `outcomes` | `resolved_by` | Which operator closed a case | Staff identity |
| `audit_log` | `details_json` → `note` | Free text an operator typed when resolving a case | Operator-authored, unbounded in content |

**What is deliberately absent, and worth stating because its absence is the strongest
property here:** no name, no email address, no postal address, no phone number, no card
number, no PAN or last-four, no expiry, no CVV, no token or mandate reference, no IP
address, and no device or user-agent string. The platform never receives cardholder
data — it reads the gateway's *decision* about a charge, not the instrument. It is
therefore outside PCI DSS cardholder-data scope, though a deployment is still
responsible for the environment it runs in.

The identifiers it does hold are pseudonymous in the GDPR sense: they do not identify a
person on their own, and they do identify one to anyone holding the Razorpay account.
That is exactly why they are treated as sensitive in logs (§3) even though they are
stored in the clear in the database (§2).

## 2. Why the identifiers are stored unmasked in the database

Deliberate, not an oversight. `payment_id` and `attempt_id` are the idempotency key:
`UNIQUE (tenant_id, payment_id, attempt_id)` is what makes a replayed webhook return the
first decision instead of charging a customer twice. A digest could serve that purpose,
but `customer_id` is also what an operator uses to find a case, what the retry actually
has to be submitted against, and what makes a decision explainable after the fact.
Masking in the primary store would break the product and protect nothing: the database
is the asset the access controls exist to guard, and it is already behind
authentication, per-request role checks, and tenant scoping.

The exposure that masking addresses is a different one, and it is the log file.

## 3. What reaches the logs, after Phase 14

Logs travel where the database does not — a shipper, a laptop, a support ticket, a
screenshot in a chat. So the rule applied throughout is: a log line may carry enough to
correlate and diagnose, and not enough to look a customer up in the Razorpay dashboard
or to authenticate as anyone.

**Gateway identifiers are masked** by `observability.mask_identifier()`: a readable
four-character prefix, then a truncated SHA-256 of the whole value — `pay_***138504fc6bc7`.
Deterministic, so two lines about the same payment still join; not a copy-and-paste path
into a gateway dashboard. This is masking, not anonymisation, and the docstring says so:
an attacker holding a list of candidate identifiers can hash them and match. It removes
the realistic exposure for a log file, not a determined correlation attack.

The internal `event_id` is left readable on purpose. It is this service's own row id, it
means nothing outside this database, and it is what an operator needs to pull the full
record out of the audit trail.

**Secret-named keys are never emitted.** `observability.redact()` runs over every
record the JSON formatter emits and replaces the value of any key named `password`,
`token`, `access_token`, `authorization`, `signature`, `secret`, `jwt_secret_key`,
`razorpay_webhook_secret`, `api_key`, `gemini_api_key`, `key_secret`, or `message_body`
with `<redacted>`. This is defence in depth: no call site passes a secret, and if one
ever does it still does not reach the sink.

**Tracebacks are not logged.** `JsonFormatter` reduces an exception to `error_type` and
`error_message`. A traceback in a structured log line is noise, and frame locals can
quote input the record should not carry.

**Customer-facing message bodies are not logged.** `LoggingNotificationProvider` records
the masked payment id, the action category, and `message_length` — never the prose. The
body is retrievable from the audit trail by `event_id` if it is ever needed.

**Credentials quoted by third-party exceptions are stripped.**
`observability.safe_error_text()` removes a URL userinfo password
(`postgresql+psycopg://revenue:<redacted>@db.internal:5432/recovery`) and a
secret-named query parameter (`?key=<redacted>`) before the text is stored in
`tasks.last_error` or shown to an operator. Two real shapes motivated it: a SQLAlchemy
connection error quotes the URL it dialled, and Google's Generative Language REST API
takes its key as `?key=`.

**Database URLs are logged through `safe_database_url()`.** The worker's startup line
used to log `self.database.url` directly, which wrote the PostgreSQL password into every
log sink on every start. Fixed in Phase 14.

**What is intentionally *not* stripped:** parameter values a database driver
interpolated into a failing statement, such as `UNIQUE constraint failed:
payment_events.payment_id [pay_abc]`. They are the identifiers already stored in that
same tenant's own `payment_events` row, so removing them would cost an operator the
diagnosis and disclose nothing new.

### Fields written to the audit trail

`audit_log.details_json` carries the decision, the guardrail that produced it, the four
scores, the model version, the executed detail, and the task id — and **no raw customer
or payment identifier**. It references the event by `event_id` instead. That is the
right shape: the identifiers live once, in `payment_events`, and every other table
points at them.

The one field to be aware of is `note` on a `CASE_RESOLVED` entry. It is free text an
operator typed, bounded to 500 characters by `models.py`, and it can contain whatever
they chose to paste. That is inherent to a human-review record — the note is the point —
and it is not something to strip. It is called out here so a data-subject request knows
to look there.

## 4. Access controls that already limit exposure

- Every read is scoped by `tenant_id`; one tenant's operator cannot see or resolve
  another's cases.
- Every request re-reads the account row, so a deactivated operator is refused
  immediately rather than at token expiry.
- Roles rank `VIEWER(1) < OPERATOR(2) < ADMIN(3)` and fail closed at rank 0. No role
  grants a guardrail override, `ADMIN` included.
- The Next.js control centre holds the API token in an httpOnly, `SameSite=Strict`,
  `Secure` cookie; browser JavaScript never holds a credential that authorises a
  payment action.
- Production refuses to boot with the published `JWT_SECRET_KEY` or the published
  `RAZORPAY_WEBHOOK_SECRET`.

## 5. Retention: the current stance, and what is not enforced

**Stated stance.** These are the retention periods this platform is designed around.

| Data | Intended retention | Reason |
| --- | --- | --- |
| `payment_events`, `decisions`, `outcomes`, `scores` | 24 months from `created_at` | A recovery decision is a financial record. Indian bookkeeping practice and dispute windows both want more than a year, and the model's own evaluation needs a full seasonal cycle. |
| `audit_log` | 24 months, aligned with the event it references | An audit entry that outlives its event, or dies before it, is worse than none. |
| `tasks` | 90 days after reaching `DONE` or `FAILED` | Operationally interesting only while somebody might still act on it. A `FAILED` row is kept, not deleted, because an approved action that never ran is a fact somebody has to see. |
| `users` | For the life of the account, plus the audit references to it | `resolved_by` in `outcomes` must stay resolvable, so an operator row is deactivated (`is_active = 0`), not deleted. |
| Application logs | 30 days at the sink | Long enough to investigate an incident; short enough that a masked identifier's correlation value expires. Not enforced by this codebase — it is a property of whatever log sink the deployment uses. |

**Not enforced in code. This is the honest part.** There is no scheduled deletion job,
no `DELETE FROM` on an age predicate anywhere in the repository, no `retention_days`
setting, and no data-subject-request endpoint. Nothing above happens automatically
today. A deployment that needs these periods enforced has to implement them, and the
shape that fits the existing architecture is a task type on the existing queue rather
than new infrastructure — `TaskType` and the durable `tasks` table already provide
scheduling, retries, and visibility.

Two things make that future work tractable rather than a rewrite:

1. Every personal-data table carries `created_at`, so an age predicate exists to write.
2. Foreign keys run one way, `payment_events` → everything else, and SQLite enforcement
   is switched on (`PRAGMA foreign_keys = ON`), so a deletion order is derivable rather
   than guessed: `audit_log`, `scores`, `decisions`, `outcomes`, `tasks`, then
   `payment_events`.

**Also not implemented:** encryption at rest (a property of the deployed volume or the
managed PostgreSQL instance, not of this code), field-level encryption, log-sink
retention enforcement, and export/erasure endpoints for a data-subject request. An
erasure request today is a manual `DELETE` in the order above.

## 6. What a reviewer should check first

1. `RAZORPAY_WEBHOOK_SECRET` and `JWT_SECRET_KEY` come from a secret store, not a file
   in the repository. Production refuses to boot otherwise, but confirm it anyway.
2. `LOG_FORMAT=json` in production, so masking and redaction run through
   `JsonFormatter` rather than a `%s`-formatted line a call site wrote by hand.
3. The log sink has a retention period configured. This codebase cannot set it.
4. `FRONTEND_COOKIE_SECURE` is not `false`.
5. Whether the deployment needs §5 enforced. If it does, that is a build, not a config
   change, and this document is where the requirement is written down.
