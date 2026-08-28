from revenue_recovery.models import PaymentEventCreate, RecoveryAction


def test_processes_event_and_records_metrics(service, event_payload: dict) -> None:
    result = service.process_event(PaymentEventCreate.model_validate(event_payload))
    assert result.action is RecoveryAction.RETRY_LATER
    assert result.retry_delay_hours == 1
    assert result.recovery_probability is not None
    assert result.model_version == "recovery-logistic-v1"
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


def test_priority_cases_are_ranked(service, event_payload: dict) -> None:
    for index, amount in enumerate((499.0, 1499.0, 4999.0)):
        payload = event_payload | {
            "payment_id": f"pay_{index}", "attempt_id": f"attempt_{index}",
            "amount": amount, "subscription_value": amount,
            "previous_failure_count": index + 1,
        }
        service.process_event(PaymentEventCreate.model_validate(payload))
    cases = service.get_top_priority_cases(3)
    assert len(cases) == 3
    assert [case.priority_score for case in cases] == sorted(
        [case.priority_score for case in cases], reverse=True
    )


def test_fraud_is_not_retried_by_baseline(service, event_payload: dict) -> None:
    event_payload["failure_code"] = "fraud_suspected"
    result = service.process_event(PaymentEventCreate.model_validate(event_payload))
    assert result.action is RecoveryAction.STOP_RECOVERY
    assert result.recovered is None


def test_an_escalated_case_carries_the_models_view(service, event_payload: dict) -> None:
    """A case sent to a person is scored, even though a guardrail blocked it.

    The reviewer needs the probability and priority to decide, the queue is ordered
    by priority, and the retry they may approve is re-decided from this score — an
    unscored escalation would sit at probability zero and could never be retried.
    """
    high_value = event_payload | {"amount": 60000.0, "subscription_value": 60000.0}
    result = service.process_event(PaymentEventCreate.model_validate(high_value))
    assert result.action is RecoveryAction.ESCALATE_TO_HUMAN
    assert result.recovery_probability is not None
    assert result.priority_score is not None
    assert service.get_review_queue()[0].recovery_probability == result.recovery_probability


def test_a_stopped_case_is_not_scored(service, event_payload: dict) -> None:
    """Fraud declines and capped retries are finished, so the model is not consulted.

    Nothing downstream reads their probability, and scoring a case no one may act on
    would only invite someone to act on it.
    """
    fraud = event_payload | {"failure_code": "fraud_suspected"}
    capped = event_payload | {"payment_id": "pay_capped", "attempt_id": "a_capped", "retry_count": 3}
    assert service.process_event(PaymentEventCreate.model_validate(fraud)).recovery_probability is None
    assert service.process_event(PaymentEventCreate.model_validate(capped)).recovery_probability is None

