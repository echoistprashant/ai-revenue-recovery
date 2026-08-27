# Phase 11 — Production Persistence & Durable Background Execution

## Objective

Replace the single-file SQLite prototype storage and the in-request execution of
recovery actions with a production persistence layer and a durable work queue:
one dialect-neutral data access layer serving SQLite (dev, tests, CI) and
PostgreSQL (production), schema changes owned by Alembic migrations, and approved
actions executed by a separate worker process that survives restarts.

## Why this was needed

Two prototype shortcuts had to go before any production deployment:

1. **`sqlite3` directly, with `CREATE TABLE IF NOT EXISTS` strings.** There was no
   migration path, no way to run on a real database server, and the schema existed
   only as SQL literals inside the access layer.
2. **Retries and notifications executed inside the request that ingested the
   event.** That is acceptable for a synthetic batch and wrong for production: a
   `RETRY_LATER` scheduled 24 hours out did not survive a process restart, and a
   slow notification provider blocked webhook ingestion.

## Implemented

### Dual-driver persistence

- `src/revenue_recovery/schema.py` — single source of truth for the DDL as
  SQLAlchemy Core `Table` objects, including constraints (`amount > 0`, score
  ranges), unique keys, and indexes that previously lived in ad-hoc SQL.
- `src/revenue_recovery/database.py` — `normalize_database_url` accepts a
  filesystem path, a bare path string, `sqlite://`, `postgres://`,
  `postgresql://`, or `postgresql+psycopg://` and returns one canonical URL, so
  existing `REVENUE_RECOVERY_DATABASE` call sites needed no change. SQLite gets
  `foreign_keys=ON`, WAL journaling, and a 30s busy timeout; PostgreSQL gets
  `pool_pre_ping` and a bounded pool.
- `src/revenue_recovery/clock.py` — all timestamps are UTC ISO-8601 **text**.
  Text behaves identically on both drivers, and normalizing to a single offset
  keeps lexicographic order equal to chronological order, which the queue's
  `run_at <= :now` comparison depends on.
- All SQL in the project is dialect-neutral: named bind parameters, and
  `INSERT ... RETURNING` (SQLite ≥ 3.35 and PostgreSQL) instead of
  `cursor.lastrowid`.

### Migrations own the production schema

- `alembic.ini` + `migrations/env.py` resolve the URL from the same `Settings`
  the application uses, so `alembic upgrade head` always targets the deployment's
  database. `render_as_batch` is enabled for SQLite.
- `migrations/versions/ef01b3d6fa0c_initial_schema.py` is the baseline revision.
- `Database.initialize()` creates tables **only** on SQLite. On any other driver
  it verifies the tables exist and raises `SchemaNotMigratedError` pointing at
  `alembic upgrade head`. Creating tables implicitly in production would let a
  process boot against a database no migration had ever touched, and the two
  definitions would then drift apart silently.

### Durable background execution

- `src/revenue_recovery/tasks.py` — a `tasks` table plus a claim protocol. No
  broker: the deployment cost is "one more process", not a new piece of
  infrastructure.
  - `enqueue` is unique on `(event_id, task_type)`, so a replayed webhook cannot
    produce a second retry — event-level idempotency extended to execution.
  - `claim_due` selects candidates then takes each one with
    `UPDATE ... WHERE task_id = :id AND status = 'PENDING'`. Whichever worker's
    update reports a row is the owner. This needs no dialect-specific locking
    hint, so it behaves the same on both drivers.
  - `mark_failed` reschedules with linear backoff and, once attempts are
    exhausted, leaves the row `FAILED` rather than deleting it. An approved
    action that never executed is an operational fact somebody has to see.
  - `requeue_stale` returns rows abandoned `RUNNING` by a killed worker.
- `src/revenue_recovery/actions.py` — `ActionExecutor` is the only place that
  performs an action's side effect, and providers are injected so the simulated
  gateway can be swapped for a real client without touching decision logic.
- `src/revenue_recovery/worker.py` — `RecoveryWorker.run_once()` / `run_forever()`,
  one transaction per task so a crash costs at most one in-flight item.
- `scripts/run_worker.py` — the worker process, with `--once` for cron-style
  deployments. Handles SIGTERM so a container stop lets the current task finish.
- `GET /tasks/stats` and `POST /tasks/run-due`, surfaced in the Streamlit control
  center under **Monitoring & Data Drift → Background Recovery Queue**.

### Deployment

- `docker-compose.yml` gains a `worker` service, and a `postgres` profile with a
  PostgreSQL 16 service plus a one-shot `migrate` service.
  `POSTGRES_PASSWORD` has no default on purpose: compose fails fast rather than
  starting a database with a password that is public knowledge.
- `Dockerfile` installs the `postgres` extra and copies `alembic.ini` and
  `migrations/`, so one image serves both drivers and can run its own migrations.
- `pyproject.toml` adds `sqlalchemy`, `alembic`, and an optional `postgres`
  extra (`psycopg[binary]`) — kept optional so the default install and CI stay
  free of a driver build step.

## Guardrail invariants preserved

The queue is the one genuinely new way to trigger a financial action, so it was
built to be incapable of bypassing the decision engine:

- **A queued row carries no authority.** `ActionExecutor.execute` re-runs
  `DecisionEngine.decide` immediately before acting, and withholds the action if
  the engine no longer approves it. Time passes between approval and execution:
  the retry cap may now be reached, a gateway incident may now be active, or the
  event may have been re-classified. The queue cannot outvote the engine.
- **`FRAUD_RISK_DECLINE` remains a hard stop.** A fraud event never enqueues
  anything, and a hand-inserted retry or notification task for a fraud event is
  refused at execution time with no override path.
- **Idempotency extends to execution** via the `(event_id, task_type)` unique
  constraint.
- **The audit trail covers execution, not just decisions.** Each task writes a
  `TASK_<type>` audit row recording the re-validated action, whether it executed,
  the attempt count, and the resulting state.
- **Inline mode is unchanged and still the default.** Both modes share one
  execution path, so the recorded synthetic baselines keep their numbers.

## Verification

- **pytest: 111 passing** (62 baseline + 49 new). No existing test was modified
  to accommodate new code; the only edits to existing test files were added
  assertions and a new queued-mode fixture.
  - `tests/test_database.py` (11) — URL normalization for every accepted spelling,
    password survival, pragma enforcement, `INSERT ... RETURNING`, and the
    production branch refusing to create its own schema.
  - `tests/test_tasks.py` (10) — idempotent enqueue, due-time filtering,
    single-owner claiming, backoff, visible exhaustion, error truncation, stale
    reaping, stats.
  - `tests/test_worker.py` (11) — queued/inline equivalence, outcome and audit
    recording, and the guardrail tests that matter: hand-queued fraud retries and
    notifications, retry-cap, high-value escalation, and gateway-incident tasks
    are all withheld at execution time.
  - `tests/test_migrations.py` (4) — the migration produces the same tables,
    columns, and indexes as `METADATA`, and the service runs on a migrated
    database with no `create_all`.
  - `tests/test_config.py` (5) and `tests/test_clock.py` (6).
- **`alembic upgrade head` then `alembic check`** on a scratch SQLite database
  reports "No new upgrade operations detected". CI now runs both.
- **End-to-end queued run**: a 20-event synthetic batch in queued mode left 20
  events unresolved with work pending; `python scripts/run_worker.py --once`
  reported `{'claimed': 6, 'executed': 6, 'withheld': 0, 'failed': 0,
  'requeued': 0}`, the remaining tasks being `RETRY_LATER` items scheduled in the
  future.

## Scope & limitations

- PostgreSQL support is implemented and dialect-neutral by construction, but has
  been exercised against SQLite only in this environment; no PostgreSQL server
  was available to run the suite against. The compose `postgres` profile is the
  intended way to verify it.
- The retry provider is still `SimulatedRetryProvider`. Connecting a live gateway
  is a provider swap plus real credentials, which are not in scope here.
- Existing SQLite databases created by `create_all` should be stamped
  (`alembic stamp ef01b3d6fa0c`) rather than upgraded.
- Still open for later phases: no authentication on any route (Phase 12), the
  webhook secret still has a public default rather than failing closed
  (Phase 14), and no structured logging or backups yet (Phase 14).
