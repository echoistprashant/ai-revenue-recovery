import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS payment_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    subscription_id TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0),
    currency TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    gateway TEXT NOT NULL,
    bank TEXT NOT NULL,
    failure_code TEXT NOT NULL,
    failure_category TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    previous_success_count INTEGER NOT NULL,
    previous_failure_count INTEGER NOT NULL,
    customer_age_days INTEGER NOT NULL,
    subscription_value REAL NOT NULL,
    retry_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (payment_id, attempt_id)
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL UNIQUE,
    action TEXT NOT NULL,
    retry_delay_hours INTEGER,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES payment_events(event_id)
);

CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL UNIQUE,
    recovered INTEGER,
    recovered_amount REAL NOT NULL DEFAULT 0,
    final_state TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES payment_events(event_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES payment_events(event_id)
);

CREATE TABLE IF NOT EXISTS scores (
    score_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL UNIQUE,
    recovery_probability REAL NOT NULL CHECK (recovery_probability >= 0 AND recovery_probability <= 1),
    churn_risk REAL NOT NULL CHECK (churn_risk >= 0 AND churn_risk <= 1),
    revenue_at_risk REAL NOT NULL CHECK (revenue_at_risk >= 0),
    priority_score REAL NOT NULL CHECK (priority_score >= 0),
    model_version TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES payment_events(event_id)
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @staticmethod
    def audit(connection: sqlite3.Connection, event_id: int, event_type: str, details: dict) -> None:
        connection.execute(
            "INSERT INTO audit_log (event_id, event_type, details_json) VALUES (?, ?, ?)",
            (event_id, event_type, json.dumps(details, sort_keys=True)),
        )
