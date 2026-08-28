"""Background worker that executes queued recovery actions.

Deployment shape: one extra process (``python scripts/run_worker.py``) polling the
``tasks`` table. Claiming, executing, and recording each task happens per task, so a
crash costs at most one in-flight item, which the stale-task reaper returns to the
queue.
"""

import logging
import threading
from dataclasses import dataclass, field

from revenue_recovery.actions import ActionContext, ActionExecutor, ExecutionResult
from revenue_recovery.clock import iso_now
from revenue_recovery.config import DEFAULT_SETTINGS, Settings
from revenue_recovery.database import Database, DatabaseConnection
from revenue_recovery.models import FailureCategory
from revenue_recovery.tasks import Task, TaskQueue, TaskStatus, TaskType

LOGGER = logging.getLogger(__name__)

CONTEXT_QUERY = """
SELECT e.event_id, e.payment_id, e.failure_category, e.amount, e.retry_count,
       COALESCE(s.recovery_probability, 0.0) AS recovery_probability
FROM payment_events e
LEFT JOIN scores s ON s.event_id = e.event_id
WHERE e.event_id = :event_id
"""


@dataclass
class WorkerReport:
    claimed: int = 0
    executed: int = 0
    withheld: int = 0
    failed: int = 0
    requeued: int = 0
    task_ids: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, int]:
        return {
            "claimed": self.claimed,
            "executed": self.executed,
            "withheld": self.withheld,
            "failed": self.failed,
            "requeued": self.requeued,
        }


class RecoveryWorker:
    def __init__(
        self,
        database: Database,
        settings: Settings = DEFAULT_SETTINGS,
        executor: ActionExecutor | None = None,
        queue: TaskQueue | None = None,
    ):
        self.database = database
        self.settings = settings
        self.executor = executor or ActionExecutor()
        self.queue = queue or TaskQueue(
            max_attempts=settings.task_max_attempts,
            backoff_seconds=settings.task_retry_backoff_seconds,
        )

    def run_once(self, now: str | None = None) -> WorkerReport:
        report = WorkerReport()
        with self.database.connect() as connection:
            report.requeued = self.queue.requeue_stale(connection)
            claimed = self.queue.claim_due(connection, now=now, limit=self.settings.worker_batch_size)
        report.claimed = len(claimed)
        for task in claimed:
            self._process(task, report)
        return report

    def _process(self, task: Task, report: WorkerReport) -> None:
        try:
            with self.database.connect() as connection:
                context = self._load_context(connection, task)
                result = self.executor.execute(task.task_type, context)
                self._record(connection, task, context, result)
                self.queue.mark_done(connection, task.task_id)
        except Exception as exc:  # provider or database failure: keep the task visible
            LOGGER.exception("task execution failed", extra={"task_id": task.task_id})
            with self.database.connect() as connection:
                status = self.queue.mark_failed(connection, task, f"{type(exc).__name__}: {exc}")
            report.failed += 1
            if status is TaskStatus.FAILED:
                LOGGER.error("task exhausted its attempts", extra={"task_id": task.task_id})
            return
        report.task_ids.append(task.task_id)
        if result.executed:
            report.executed += 1
        else:
            report.withheld += 1

    def _load_context(self, connection: DatabaseConnection, task: Task) -> ActionContext:
        """Rebuild the decision inputs from the database, not from the task row.

        Only ``incident_active`` is read from the payload. In particular
        ``human_review_approved`` is never taken from a task: a queued row cannot
        claim that a person approved it, so the high-value escalation guardrail
        cannot be satisfied by writing a task.
        """
        row = connection.fetch_one(CONTEXT_QUERY, {"event_id": task.event_id})
        if row is None:
            raise LookupError(f"Task {task.task_id} references missing event {task.event_id}")
        return ActionContext(
            event_id=int(row["event_id"]),
            payment_id=str(row["payment_id"]),
            category=FailureCategory(row["failure_category"]),
            amount=float(row["amount"]),
            retry_count=int(row["retry_count"]),
            recovery_probability=float(row["recovery_probability"]),
            incident_active=bool(task.payload.get("incident_active", False)),
        )

    def _record(
        self,
        connection: DatabaseConnection,
        task: Task,
        context: ActionContext,
        result: ExecutionResult,
    ) -> None:
        if task.task_type is TaskType.EXECUTE_RETRY and result.final_state:
            connection.execute(
                """UPDATE outcomes
                   SET recovered = :recovered, recovered_amount = :amount, final_state = :final_state
                   WHERE event_id = :event_id""",
                {
                    "recovered": None if result.recovered is None else int(result.recovered),
                    "amount": context.amount if result.recovered else 0.0,
                    "final_state": result.final_state,
                    "event_id": context.event_id,
                },
            )
        self.database.audit(connection, context.event_id, f"TASK_{task.task_type.value}", {
            "task_id": task.task_id,
            "attempts": task.attempts,
            "executed": result.executed,
            "revalidated_action": result.revalidated_action.value,
            "detail": result.detail,
            "recovered": result.recovered,
            "final_state": result.final_state,
            "recorded_at": iso_now(),
        })

    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        stop = stop_event or threading.Event()
        LOGGER.info("worker started", extra={"database": self.database.url})
        while not stop.is_set():
            report = self.run_once()
            if report.claimed == 0:
                stop.wait(self.settings.worker_poll_interval_seconds)
            else:
                LOGGER.info("worker cycle complete", extra=report.as_dict())
