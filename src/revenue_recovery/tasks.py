"""Durable background work queue.

Retries and notifications used to run inside the request that ingested the event.
That is fine for a synthetic batch and wrong for production: a delayed retry has to
survive a restart, and a slow notification provider must not block ingestion.

The queue is a table plus a claim protocol, which keeps the deployment to
"one more process" instead of adding a broker. Rows record approved work only;
:class:`revenue_recovery.worker.RecoveryWorker` re-runs the decision engine before
executing anything, so a queued row never carries financial authority of its own.
"""

import json
import os
import socket
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Any

from revenue_recovery.clock import iso_now, to_iso, utc_now
from revenue_recovery.database import DatabaseConnection


class TaskType(StrEnum):
    EXECUTE_RETRY = "EXECUTE_RETRY"
    SEND_NOTIFICATION = "SEND_NOTIFICATION"


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class Task:
    task_id: int
    event_id: int
    task_type: TaskType
    status: TaskStatus
    payload: dict[str, Any]
    run_at: str
    attempts: int
    max_attempts: int


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


class TaskQueue:
    def __init__(self, max_attempts: int = 3, backoff_seconds: int = 60):
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds

    def enqueue(
        self,
        connection: DatabaseConnection,
        event_id: int,
        task_type: TaskType,
        payload: dict[str, Any],
        run_at: str | None = None,
    ) -> int | None:
        """Insert one task for an event, or return ``None`` if it already exists.

        The ``(event_id, task_type)`` uniqueness is what keeps a duplicate webhook
        from producing a second retry, mirroring event-level idempotency.
        """
        existing = connection.fetch_one(
            "SELECT task_id FROM tasks WHERE event_id = :event_id AND task_type = :task_type",
            {"event_id": event_id, "task_type": task_type.value},
        )
        if existing:
            return None
        now = iso_now()
        return connection.insert_returning_id(
            """INSERT INTO tasks (
                   event_id, task_type, status, payload_json, run_at,
                   attempts, max_attempts, created_at, updated_at
               ) VALUES (
                   :event_id, :task_type, :status, :payload_json, :run_at,
                   0, :max_attempts, :created_at, :updated_at
               )""",
            {
                "event_id": event_id,
                "task_type": task_type.value,
                "status": TaskStatus.PENDING.value,
                "payload_json": json.dumps(payload, sort_keys=True, default=str),
                "run_at": run_at or now,
                "max_attempts": self.max_attempts,
                "created_at": now,
                "updated_at": now,
            },
            "task_id",
        )

    def claim_due(
        self,
        connection: DatabaseConnection,
        now: str | None = None,
        limit: int = 20,
        worker: str | None = None,
    ) -> list[Task]:
        """Atomically take ownership of due tasks.

        The conditional ``UPDATE ... WHERE status = 'PENDING'`` is the lock: whichever
        worker's update reports a row is the owner. This needs no dialect-specific
        locking hint, so it behaves the same on SQLite and PostgreSQL.
        """
        moment = now or iso_now()
        owner = worker or worker_identity()
        candidates = connection.fetch_all(
            """SELECT task_id FROM tasks
               WHERE status = :status AND run_at <= :now
               ORDER BY run_at ASC, task_id ASC LIMIT :limit""",
            {"status": TaskStatus.PENDING.value, "now": moment, "limit": limit},
        )
        claimed: list[Task] = []
        for candidate in candidates:
            result = connection.execute(
                """UPDATE tasks
                   SET status = :running, locked_by = :owner, locked_at = :now,
                       attempts = attempts + 1, updated_at = :now
                   WHERE task_id = :task_id AND status = :pending""",
                {
                    "running": TaskStatus.RUNNING.value,
                    "pending": TaskStatus.PENDING.value,
                    "owner": owner,
                    "now": moment,
                    "task_id": candidate["task_id"],
                },
            )
            if result.rowcount != 1:
                continue
            row = connection.fetch_one(
                "SELECT * FROM tasks WHERE task_id = :task_id", {"task_id": candidate["task_id"]}
            )
            if row is not None:
                claimed.append(_to_task(row))
        return claimed

    def mark_done(self, connection: DatabaseConnection, task_id: int) -> None:
        connection.execute(
            """UPDATE tasks SET status = :status, last_error = NULL, locked_by = NULL,
                   locked_at = NULL, updated_at = :now
               WHERE task_id = :task_id""",
            {"status": TaskStatus.DONE.value, "now": iso_now(), "task_id": task_id},
        )

    def mark_failed(self, connection: DatabaseConnection, task: Task, error: str) -> TaskStatus:
        """Reschedule with linear backoff, or give up once attempts are exhausted.

        Giving up leaves the row visible as ``FAILED`` instead of deleting it: an
        unexecuted approved action is an operational fact somebody has to see.
        """
        exhausted = task.attempts >= task.max_attempts
        status = TaskStatus.FAILED if exhausted else TaskStatus.PENDING
        run_at = task.run_at if exhausted else to_iso(utc_now() + timedelta(seconds=self.backoff_seconds * task.attempts))
        connection.execute(
            """UPDATE tasks SET status = :status, last_error = :error, run_at = :run_at,
                   locked_by = NULL, locked_at = NULL, updated_at = :now
               WHERE task_id = :task_id""",
            {
                "status": status.value,
                "error": error[:1000],
                "run_at": run_at,
                "now": iso_now(),
                "task_id": task.task_id,
            },
        )
        return status

    def stats(self, connection: DatabaseConnection) -> dict[str, int]:
        rows = connection.fetch_all("SELECT status, COUNT(*) AS count FROM tasks GROUP BY status")
        counts = {status.value: 0 for status in TaskStatus}
        for row in rows:
            counts[str(row["status"])] = int(row["count"])
        counts["total"] = sum(counts[status.value] for status in TaskStatus)
        return counts

    def due_count(self, connection: DatabaseConnection, now: str | None = None) -> int:
        row = connection.fetch_one(
            "SELECT COUNT(*) AS count FROM tasks WHERE status = :status AND run_at <= :now",
            {"status": TaskStatus.PENDING.value, "now": now or iso_now()},
        )
        return int(row["count"]) if row else 0

    def requeue_stale(self, connection: DatabaseConnection, older_than_seconds: int = 900) -> int:
        """Return abandoned in-flight tasks to the queue.

        A worker killed mid-task leaves its row ``RUNNING`` forever. Nothing else in
        the system would notice, so the reaper is what keeps an approved action from
        being silently dropped by a restart.
        """
        cutoff = to_iso(utc_now() - timedelta(seconds=older_than_seconds))
        result = connection.execute(
            """UPDATE tasks SET status = :pending, locked_by = NULL, locked_at = NULL, updated_at = :now
               WHERE status = :running AND locked_at IS NOT NULL AND locked_at < :cutoff""",
            {
                "pending": TaskStatus.PENDING.value,
                "running": TaskStatus.RUNNING.value,
                "cutoff": cutoff,
                "now": iso_now(),
            },
        )
        return int(result.rowcount or 0)


def _to_task(row: Any) -> Task:
    return Task(
        task_id=int(row["task_id"]),
        event_id=int(row["event_id"]),
        task_type=TaskType(row["task_type"]),
        status=TaskStatus(row["status"]),
        payload=json.loads(row["payload_json"]),
        run_at=str(row["run_at"]),
        attempts=int(row["attempts"]),
        max_attempts=int(row["max_attempts"]),
    )
