"""Durable task queue: idempotent enqueue, atomic claiming, backoff, reaping."""

from datetime import timedelta

import pytest

from revenue_recovery.clock import from_iso, iso_now, to_iso, utc_now
from revenue_recovery.database import Database, DatabaseConnection
from revenue_recovery.models import PaymentEventCreate
from revenue_recovery.service import PaymentRecoveryService
from revenue_recovery.tasks import TaskQueue, TaskStatus, TaskType

INSERT_EVENT = """
INSERT INTO payment_events (
    payment_id, attempt_id, customer_id, subscription_id, amount, currency,
    payment_method, gateway, bank, failure_code, failure_category,
    event_timestamp, previous_success_count, previous_failure_count,
    customer_age_days, subscription_value, retry_count, created_at
) VALUES (
    :payment_id, :attempt_id, 'cust_1', 'sub_1', 1000.0, 'INR',
    'CARD', 'gw', 'bank', 'insufficient_funds', 'INSUFFICIENT_FUNDS',
    :now, 1, 0, 100, 1000.0, :retry_count, :now
)
"""


def insert_event(connection: DatabaseConnection, payment_id: str = "pay_q", retry_count: int = 0) -> int:
    return connection.insert_returning_id(
        INSERT_EVENT,
        {"payment_id": payment_id, "attempt_id": f"att_{payment_id}", "now": iso_now(), "retry_count": retry_count},
        "event_id",
    )


@pytest.fixture
def database(tmp_path) -> Database:
    database = Database(tmp_path / "queue.db")
    database.initialize()
    yield database
    database.dispose()


def test_enqueue_is_idempotent_per_event_and_type(database: Database) -> None:
    queue = TaskQueue()
    with database.connect() as connection:
        event_id = insert_event(connection)
        first = queue.enqueue(connection, event_id, TaskType.EXECUTE_RETRY, {})
        second = queue.enqueue(connection, event_id, TaskType.EXECUTE_RETRY, {})
        other_type = queue.enqueue(connection, event_id, TaskType.SEND_NOTIFICATION, {})
    assert first is not None
    # A replayed webhook must not be able to produce a second retry.
    assert second is None
    assert other_type is not None


def test_claim_skips_tasks_that_are_not_due_yet(database: Database) -> None:
    queue = TaskQueue()
    future = to_iso(utc_now() + timedelta(hours=6))
    with database.connect() as connection:
        event_id = insert_event(connection)
        queue.enqueue(connection, event_id, TaskType.EXECUTE_RETRY, {}, run_at=future)
        assert queue.claim_due(connection) == []
        assert queue.due_count(connection) == 0
        assert queue.claim_due(connection, now=to_iso(utc_now() + timedelta(hours=7))) != []


def test_claiming_takes_ownership_exactly_once(database: Database) -> None:
    queue = TaskQueue()
    with database.connect() as connection:
        event_id = insert_event(connection)
        queue.enqueue(connection, event_id, TaskType.EXECUTE_RETRY, {})
        claimed = queue.claim_due(connection, worker="worker-a")
        assert len(claimed) == 1
        assert claimed[0].attempts == 1
        assert claimed[0].status is TaskStatus.RUNNING
        # A second worker polling the same row finds nothing to take.
        assert queue.claim_due(connection, worker="worker-b") == []
        row = connection.fetch_one(
            "SELECT locked_by FROM tasks WHERE task_id = :id", {"id": claimed[0].task_id}
        )
        assert row["locked_by"] == "worker-a"


def test_mark_done_clears_the_lock(database: Database) -> None:
    queue = TaskQueue()
    with database.connect() as connection:
        event_id = insert_event(connection)
        task_id = queue.enqueue(connection, event_id, TaskType.EXECUTE_RETRY, {})
        task = queue.claim_due(connection)[0]
        queue.mark_done(connection, task.task_id)
        row = connection.fetch_one("SELECT * FROM tasks WHERE task_id = :id", {"id": task_id})
    assert row["status"] == TaskStatus.DONE.value
    assert row["locked_by"] is None
    assert row["locked_at"] is None


def test_failure_reschedules_with_backoff_then_gives_up_visibly(database: Database) -> None:
    queue = TaskQueue(max_attempts=2, backoff_seconds=60)
    with database.connect() as connection:
        event_id = insert_event(connection)
        queue.enqueue(connection, event_id, TaskType.EXECUTE_RETRY, {})

        first = queue.claim_due(connection)[0]
        assert queue.mark_failed(connection, first, "provider timeout") is TaskStatus.PENDING
        row = connection.fetch_one("SELECT * FROM tasks WHERE task_id = :id", {"id": first.task_id})
        assert row["last_error"] == "provider timeout"
        assert from_iso(str(row["run_at"])) > utc_now()

        second = queue.claim_due(connection, now=to_iso(utc_now() + timedelta(minutes=5)))[0]
        assert second.attempts == 2
        assert queue.mark_failed(connection, second, "provider timeout") is TaskStatus.FAILED
        row = connection.fetch_one("SELECT * FROM tasks WHERE task_id = :id", {"id": second.task_id})
    # An approved action that never executed stays on the books for an operator.
    assert row is not None
    assert row["status"] == TaskStatus.FAILED.value


def test_long_error_text_is_truncated(database: Database) -> None:
    queue = TaskQueue()
    with database.connect() as connection:
        event_id = insert_event(connection)
        queue.enqueue(connection, event_id, TaskType.EXECUTE_RETRY, {})
        task = queue.claim_due(connection)[0]
        queue.mark_failed(connection, task, "x" * 5000)
        row = connection.fetch_one("SELECT last_error FROM tasks WHERE task_id = :id", {"id": task.task_id})
    assert len(str(row["last_error"])) == 1000


def test_stale_running_tasks_are_returned_to_the_queue(database: Database) -> None:
    queue = TaskQueue()
    with database.connect() as connection:
        event_id = insert_event(connection)
        queue.enqueue(connection, event_id, TaskType.EXECUTE_RETRY, {})
        task = queue.claim_due(connection)[0]
        assert queue.requeue_stale(connection, older_than_seconds=900) == 0

        # Simulate a worker that died holding the row.
        connection.execute(
            "UPDATE tasks SET locked_at = :stale WHERE task_id = :id",
            {"stale": to_iso(utc_now() - timedelta(hours=2)), "id": task.task_id},
        )
        assert queue.requeue_stale(connection, older_than_seconds=900) == 1
        row = connection.fetch_one("SELECT * FROM tasks WHERE task_id = :id", {"id": task.task_id})
    assert row["status"] == TaskStatus.PENDING.value
    assert row["locked_by"] is None


def test_stats_report_every_status(database: Database) -> None:
    queue = TaskQueue()
    with database.connect() as connection:
        first = insert_event(connection, "pay_a")
        second = insert_event(connection, "pay_b")
        queue.enqueue(connection, first, TaskType.EXECUTE_RETRY, {})
        done_id = queue.enqueue(connection, second, TaskType.EXECUTE_RETRY, {})
        queue.mark_done(connection, done_id)
        stats = queue.stats(connection)
    assert stats["PENDING"] == 1
    assert stats["DONE"] == 1
    assert stats["RUNNING"] == 0
    assert stats["FAILED"] == 0
    assert stats["total"] == 2


def test_payload_round_trips_through_the_queue(database: Database) -> None:
    queue = TaskQueue()
    with database.connect() as connection:
        event_id = insert_event(connection)
        queue.enqueue(connection, event_id, TaskType.SEND_NOTIFICATION, {"approved_action": "SEND_NOTIFICATION"})
        task = queue.claim_due(connection)[0]
    assert task.payload == {"approved_action": "SEND_NOTIFICATION"}
    assert task.task_type is TaskType.SEND_NOTIFICATION


def test_inline_mode_leaves_no_pending_work(service: PaymentRecoveryService, event_payload: dict) -> None:
    service.process_event(PaymentEventCreate(**event_payload))
    stats = service.get_task_stats()
    assert stats["PENDING"] == 0
    assert stats["execution_mode"] == "inline"
