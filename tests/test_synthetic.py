from revenue_recovery.synthetic import generate_events


def test_generator_is_reproducible() -> None:
    first = generate_events(10, 42)
    second = generate_events(10, 42)
    assert [event.model_dump() for event in first] == [event.model_dump() for event in second]


def test_synthetic_batch_flows_end_to_end(service) -> None:
    events = generate_events(200, 20260827)
    for event in events:
        service.process_event(event)
    metrics = service.get_metrics()
    assert metrics.total_failures == 200
    assert metrics.resolved_events > 0
    assert metrics.recovered_events > 0
    assert len(metrics.failure_breakdown) == 9
