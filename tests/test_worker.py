"""Background worker behaviour, with the guardrail invariants it must preserve.

The load-bearing tests here are the ones that hand the worker a task it should
refuse. A queued row is a record of a past approval, not authority to act, so the
worker re-runs the decision engine and withholds anything the engine no longer
approves — that is what stops the queue from becoming a way around the guardrails.
"""

import json
from dataclasses import replace
from datetime import timedelta

import pytest

from revenue_recovery.actions import ActionExecutor
from revenue_recovery.clock import to_iso, utc_now
from revenue_recovery.models import PaymentEventCreate, RecoveryAction
from revenue_recovery.service import PaymentRecoveryService
from revenue_recovery.tasks import TaskQueue, TaskStatus, TaskType
from revenue_recovery.worker import RecoveryWorker


def audit_entries(service: PaymentRecoveryService, event_id: int) -> list[dict]:
    with service.database.connect() as connection:
        rows = connection.fetch_all(
            "SELECT event_type, details_json FROM audit_log WHERE event_id = :id ORDER BY audit_id",
            {"id": event_id},
        )
    return [{"event_type": row["event_type"], **json.loads(row["details_json"])} for row in rows]


def test_queued_mode_defers_execution_to_the_worker(
    queued_service: PaymentRecoveryService, event_payload: dict
) -> None:
    processed = queued_service.process_event(PaymentEventCreate(**event_payload))
    assert processed.action in {RecoveryAction.RETRY_NOW, RecoveryAction.RETRY_LATER}
    # Nothing has been attempted yet, so the outcome is genuinely unknown.
    assert processed.recovered is None

    with queued_service.database.connect() as connection:
        outcome = connection.fetch_one(
            "SELECT final_state FROM outcomes WHERE event_id = :id", {"id": processed.event_id}
        )
        task = connection.fetch_one(
            "SELECT status, task_type FROM tasks WHERE event_id = :id", {"id": processed.event_id}
        )
    assert outcome["final_state"] == "SCHEDULED"
    assert task["status"] == TaskStatus.PENDING.value
    assert task["task_type"] == TaskType.EXECUTE_RETRY.value


def test_worker_executes_due_work_and_records_the_outcome(
    queued_service: PaymentRecoveryService, event_payload: dict
) -> None:
    processed = queued_service.process_event(PaymentEventCreate(**event_payload))
    report = queued_service.run_due_tasks(now=to_iso(utc_now() + timedelta(days=2)))

    assert report["claimed"] == 1
    assert report["executed"] == 1
    assert report["failed"] == 0

    with queued_service.database.connect() as connection:
        outcome = connection.fetch_one(
            "SELECT recovered, final_state FROM outcomes WHERE event_id = :id", {"id": processed.event_id}
        )
        task = connection.fetch_one(
            "SELECT status FROM tasks WHERE event_id = :id", {"id": processed.event_id}
        )
    assert outcome["final_state"] in {"RECOVERED", "UNRESOLVED"}
    assert outcome["recovered"] is not None
    assert task["status"] == TaskStatus.DONE.value

    audit = audit_entries(queued_service, processed.event_id)
    assert [entry["event_type"] for entry in audit] == ["EVENT_PROCESSED", "TASK_EXECUTE_RETRY"]
    assert audit[-1]["executed"] is True
    assert audit[-1]["revalidated_action"] in {"RETRY_NOW", "RETRY_LATER"}


def test_queued_and_inline_reach_the_same_outcome(
    service: PaymentRecoveryService, queued_service: PaymentRecoveryService, event_payload: dict
) -> None:
    """Switching execution mode must not change what happens to a payment."""
    inline = service.process_event(PaymentEventCreate(**event_payload))
    queued = queued_service.process_event(PaymentEventCreate(**event_payload))
    queued_service.run_due_tasks(now=to_iso(utc_now() + timedelta(days=2)))

    with queued_service.database.connect() as connection:
        queued_outcome = connection.fetch_one(
            "SELECT recovered FROM outcomes WHERE event_id = :id", {"id": queued.event_id}
        )
    assert queued.action is inline.action
    assert bool(queued_outcome["recovered"]) is bool(inline.recovered)


def queue_task_directly(
    service: PaymentRecoveryService, event_id: int, task_type: TaskType, payload: dict | None = None
) -> int:
    """Insert a task without going through the service.

    This stands in for a stale queue row, a replayed message, or a future code path
    that tries to schedule work directly — the worker must still consult the engine.
    """
    with service.database.connect() as connection:
        connection.execute("DELETE FROM tasks WHERE event_id = :id", {"id": event_id})
        return TaskQueue().enqueue(connection, event_id, task_type, payload or {})


@pytest.mark.parametrize("task_type", [TaskType.EXECUTE_RETRY, TaskType.SEND_NOTIFICATION])
def test_fraud_decline_is_never_executed_from_the_queue(
    queued_service: PaymentRecoveryService, event_payload: dict, task_type: TaskType
) -> None:
    processed = queued_service.process_event(
        PaymentEventCreate(**(event_payload | {"failure_code": "fraud_suspected"}))
    )
    assert processed.action is RecoveryAction.STOP_RECOVERY

    queue_task_directly(queued_service, processed.event_id, task_type)
    report = queued_service.run_due_tasks()

    assert report["claimed"] == 1
    assert report["executed"] == 0
    assert report["withheld"] == 1

    audit = audit_entries(queued_service, processed.event_id)
    assert audit[-1]["executed"] is False
    assert audit[-1]["revalidated_action"] == RecoveryAction.STOP_RECOVERY.value


def test_retry_cap_still_blocks_a_queued_retry(
    queued_service: PaymentRecoveryService, event_payload: dict
) -> None:
    processed = queued_service.process_event(
        PaymentEventCreate(**(event_payload | {"retry_count": 3}))
    )
    assert processed.action is not RecoveryAction.RETRY_NOW

    queue_task_directly(queued_service, processed.event_id, TaskType.EXECUTE_RETRY)
    report = queued_service.run_due_tasks()

    assert report["withheld"] == 1
    with queued_service.database.connect() as connection:
        outcome = connection.fetch_one(
            "SELECT recovered, final_state FROM outcomes WHERE event_id = :id", {"id": processed.event_id}
        )
    assert outcome["recovered"] is None
    assert outcome["final_state"] == "WITHHELD"


def test_high_value_escalation_is_not_executed_as_a_retry(
    queued_service: PaymentRecoveryService, event_payload: dict
) -> None:
    processed = queued_service.process_event(
        PaymentEventCreate(**(event_payload | {"amount": 75000.0, "subscription_value": 75000.0}))
    )
    assert processed.action is RecoveryAction.ESCALATE_TO_HUMAN

    queue_task_directly(queued_service, processed.event_id, TaskType.EXECUTE_RETRY)
    report = queued_service.run_due_tasks()
    assert report["executed"] == 0
    assert report["withheld"] == 1


def test_gateway_incident_in_the_payload_suppresses_the_retry(
    queued_service: PaymentRecoveryService, event_payload: dict
) -> None:
    processed = queued_service.process_event(PaymentEventCreate(**event_payload))
    queue_task_directly(
        queued_service, processed.event_id, TaskType.EXECUTE_RETRY, {"incident_active": True}
    )
    report = queued_service.run_due_tasks()
    assert report["executed"] == 0
    assert report["withheld"] == 1


def test_a_task_pointing_at_a_missing_event_is_refused(
    queued_service: PaymentRecoveryService, event_payload: dict
) -> None:
    queued_service.process_event(PaymentEventCreate(**event_payload))
    with queued_service.database.connect() as connection:
        task = TaskQueue().claim_due(connection, now=to_iso(utc_now() + timedelta(days=2)))[0]
        orphan = replace(task, event_id=999999)
        with pytest.raises(LookupError):
            queued_service.worker._load_context(connection, orphan)


class ExplodingRetryProvider:
    def attempt_retry(self, context) -> bool:
        raise RuntimeError("gateway unreachable")


def test_provider_failure_keeps_the_task_visible_and_retries_it(
    queued_service: PaymentRecoveryService, event_payload: dict
) -> None:
    processed = queued_service.process_event(PaymentEventCreate(**event_payload))
    settings = replace(queued_service.settings, task_retry_backoff_seconds=1)
    worker = RecoveryWorker(
        queued_service.database,
        settings,
        ActionExecutor(retry_provider=ExplodingRetryProvider()),
        TaskQueue(max_attempts=settings.task_max_attempts, backoff_seconds=1),
    )

    def cycle(days: int) -> None:
        report = worker.run_once(now=to_iso(utc_now() + timedelta(days=days)))
        assert report.failed == 1
        assert report.executed == 0

    def task_row() -> dict:
        with queued_service.database.connect() as connection:
            return dict(
                connection.fetch_one(
                    "SELECT status, attempts, last_error FROM tasks WHERE event_id = :id",
                    {"id": processed.event_id},
                )
            )

    # The row carries max_attempts (3), so it is retried twice before being given up on.
    cycle(2)
    assert task_row()["status"] == TaskStatus.PENDING.value
    assert "RuntimeError" in str(task_row()["last_error"])
    cycle(3)
    assert task_row()["status"] == TaskStatus.PENDING.value
    cycle(4)

    row = task_row()
    with queued_service.database.connect() as connection:
        outcome = connection.fetch_one(
            "SELECT recovered, final_state FROM outcomes WHERE event_id = :id", {"id": processed.event_id}
        )
    # Exhausted, but still on the books: an approved action that never ran is an
    # operational fact, not something to delete.
    assert row["status"] == TaskStatus.FAILED.value
    assert row["attempts"] == 3
    assert outcome["recovered"] is None
    assert outcome["final_state"] == "SCHEDULED"


def test_worker_report_counts_requeued_tasks(
    queued_service: PaymentRecoveryService, event_payload: dict
) -> None:
    processed = queued_service.process_event(PaymentEventCreate(**event_payload))
    with queued_service.database.connect() as connection:
        connection.execute(
            """UPDATE tasks SET status = :running, locked_by = 'dead-worker', locked_at = :stale
               WHERE event_id = :id""",
            {
                "running": TaskStatus.RUNNING.value,
                "stale": to_iso(utc_now() - timedelta(hours=2)),
                "id": processed.event_id,
            },
        )
    report = queued_service.run_due_tasks(now=to_iso(utc_now() + timedelta(days=2)))
    assert report["requeued"] == 1
    assert report["claimed"] == 1
