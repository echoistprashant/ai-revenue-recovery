from revenue_recovery.models import BaselineAction, PaymentEventCreate


def test_processes_event_and_records_metrics(service, event_payload: dict) -> None:
    result = service.process_event(PaymentEventCreate.model_validate(event_payload))
    assert result.action is BaselineAction.RETRY_LATER
    assert result.retry_delay_hours == 1
    metrics = service.get_metrics()
    assert metrics.total_failures == 1
    assert metrics.failure_breakdown["INSUFFICIENT_FUNDS"] == 1


def test_duplicate_event_returns_existing_result(service, event_payload: dict) -> None:
    event = PaymentEventCreate.model_validate(event_payload)
    first = service.process_event(event)
    duplicate = service.process_event(event)
    assert duplicate.duplicate is True
    assert duplicate.event_id == first.event_id
    assert service.get_metrics().total_failures == 1


def test_fraud_is_not_retried_by_baseline(service, event_payload: dict) -> None:
    event_payload["failure_code"] = "fraud_suspected"
    result = service.process_event(PaymentEventCreate.model_validate(event_payload))
    assert result.action is BaselineAction.STOP_RECOVERY
    assert result.recovered is None
