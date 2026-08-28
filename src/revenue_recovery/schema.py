"""Single source of truth for the relational schema.

The same ``MetaData`` powers three consumers:

- ``Database.initialize()`` for local, container, and test bootstrap
- Alembic migrations for the production PostgreSQL path
- the textual SQL in ``service.py`` and ``tasks.py``

Every column type is chosen to behave identically on SQLite and PostgreSQL.
Timestamps are stored as UTC ISO-8601 text and nullable booleans as integers,
which is what the pre-PostgreSQL SQLite schema already did, so existing
databases and queries keep their meaning.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

METADATA = MetaData()

TIMESTAMP = String(64)

DEFAULT_TENANT = "default"

# Operator accounts. Passwords are stored only as bcrypt hashes; nothing in this
# table can be used to sign a token on its own, and no row grants the ability to
# override a guardrail — role only widens which routes a request may reach.
users = Table(
    "users",
    METADATA,
    Column("user_id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(80), nullable=False),
    Column("password_hash", String(200), nullable=False),
    Column("role", String(20), nullable=False),
    Column("tenant_id", String(80), nullable=False, server_default=DEFAULT_TENANT),
    Column("is_active", Integer, nullable=False, server_default="1"),
    Column("created_at", TIMESTAMP, nullable=False),
    Column("last_login_at", TIMESTAMP),
    CheckConstraint("role IN ('VIEWER', 'OPERATOR', 'ADMIN')", name="ck_users_role_known"),
    UniqueConstraint("username", name="uq_users_username"),
    Index("ix_users_tenant_id", "tenant_id"),
)

payment_events = Table(
    "payment_events",
    METADATA,
    Column("event_id", Integer, primary_key=True, autoincrement=True),
    # Every event belongs to exactly one tenant. Reads are filtered by it rather
    # than relying on callers to remember, so one tenant's operator cannot see or
    # resolve another tenant's cases.
    Column("tenant_id", String(80), nullable=False, server_default=DEFAULT_TENANT),
    Column("payment_id", String(100), nullable=False),
    Column("attempt_id", String(100), nullable=False),
    Column("customer_id", String(100), nullable=False),
    Column("subscription_id", String(100), nullable=False),
    Column("amount", Float, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("payment_method", String(20), nullable=False),
    Column("gateway", String(100), nullable=False),
    Column("bank", String(100), nullable=False),
    Column("failure_code", String(100), nullable=False),
    Column("failure_category", String(40), nullable=False),
    Column("event_timestamp", TIMESTAMP, nullable=False),
    Column("previous_success_count", Integer, nullable=False),
    Column("previous_failure_count", Integer, nullable=False),
    Column("customer_age_days", Integer, nullable=False),
    Column("subscription_value", Float, nullable=False),
    Column("retry_count", Integer, nullable=False),
    Column("created_at", TIMESTAMP, nullable=False),
    CheckConstraint("amount > 0", name="ck_payment_events_amount_positive"),
    # Idempotency is scoped to the tenant: a gateway identifier only has meaning
    # inside the account that issued it, and a global key would let one tenant
    # discover another's payment IDs through the duplicate response.
    UniqueConstraint("tenant_id", "payment_id", "attempt_id", name="uq_payment_events_tenant_payment_attempt"),
    Index("ix_payment_events_customer_id", "customer_id"),
    Index("ix_payment_events_failure_category", "failure_category"),
    Index("ix_payment_events_created_at", "created_at"),
    Index("ix_payment_events_tenant_id", "tenant_id"),
)

decisions = Table(
    "decisions",
    METADATA,
    Column("decision_id", Integer, primary_key=True, autoincrement=True),
    Column("event_id", Integer, ForeignKey("payment_events.event_id"), nullable=False, unique=True),
    Column("action", String(40), nullable=False),
    Column("retry_delay_hours", Integer),
    Column("reason", Text, nullable=False),
    Column("created_at", TIMESTAMP, nullable=False),
    Index("ix_decisions_action", "action"),
)

outcomes = Table(
    "outcomes",
    METADATA,
    Column("outcome_id", Integer, primary_key=True, autoincrement=True),
    Column("event_id", Integer, ForeignKey("payment_events.event_id"), nullable=False, unique=True),
    Column("recovered", Integer),
    Column("recovered_amount", Float, nullable=False, default=0.0),
    Column("final_state", String(30), nullable=False),
    Column("created_at", TIMESTAMP, nullable=False),
    # Set only when a human closes an escalated case. Who acted is part of the
    # record, not just the fact that something changed.
    Column("resolved_by", String(80)),
    Column("resolved_at", TIMESTAMP),
    Index("ix_outcomes_final_state", "final_state"),
)

audit_log = Table(
    "audit_log",
    METADATA,
    Column("audit_id", Integer, primary_key=True, autoincrement=True),
    Column("event_id", Integer, ForeignKey("payment_events.event_id"), nullable=False),
    Column("event_type", String(50), nullable=False),
    Column("details_json", Text, nullable=False),
    Column("created_at", TIMESTAMP, nullable=False),
    Index("ix_audit_log_event_id", "event_id"),
    Index("ix_audit_log_created_at", "created_at"),
)

scores = Table(
    "scores",
    METADATA,
    Column("score_id", Integer, primary_key=True, autoincrement=True),
    Column("event_id", Integer, ForeignKey("payment_events.event_id"), nullable=False, unique=True),
    Column("recovery_probability", Float, nullable=False),
    Column("churn_risk", Float, nullable=False),
    Column("revenue_at_risk", Float, nullable=False),
    Column("priority_score", Float, nullable=False),
    Column("model_version", String(60), nullable=False),
    Column("created_at", TIMESTAMP, nullable=False),
    CheckConstraint("recovery_probability >= 0 AND recovery_probability <= 1", name="ck_scores_probability_range"),
    CheckConstraint("churn_risk >= 0 AND churn_risk <= 1", name="ck_scores_churn_range"),
    CheckConstraint("revenue_at_risk >= 0", name="ck_scores_revenue_non_negative"),
    CheckConstraint("priority_score >= 0", name="ck_scores_priority_non_negative"),
    Index("ix_scores_priority_score", "priority_score"),
)

# Background work items. Only actions the decision engine already approved are
# enqueued here, and the worker re-runs the engine before execution, so a queued
# row is never independent authority to move money.
tasks = Table(
    "tasks",
    METADATA,
    Column("task_id", Integer, primary_key=True, autoincrement=True),
    Column("event_id", Integer, ForeignKey("payment_events.event_id"), nullable=False),
    Column("task_type", String(40), nullable=False),
    Column("status", String(20), nullable=False),
    Column("payload_json", Text, nullable=False),
    Column("run_at", TIMESTAMP, nullable=False),
    Column("attempts", Integer, nullable=False, default=0),
    Column("max_attempts", Integer, nullable=False, default=3),
    Column("last_error", Text),
    Column("locked_by", String(80)),
    Column("locked_at", TIMESTAMP),
    Column("created_at", TIMESTAMP, nullable=False),
    Column("updated_at", TIMESTAMP, nullable=False),
    UniqueConstraint("event_id", "task_type", name="uq_tasks_event_type"),
    Index("ix_tasks_status_run_at", "status", "run_at"),
)

ALL_TABLES = (payment_events, decisions, outcomes, audit_log, scores, tasks, users)
