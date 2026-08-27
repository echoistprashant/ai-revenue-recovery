from revenue_recovery.experimentation import ExperimentEvent, assign_variant, project_what_if, run_experiment


def events() -> list[ExperimentEvent]:
    return [ExperimentEvent(f"e-{i}", 100 + i, ((i * 37) % 100) / 100) for i in range(500)]


def test_assignment_is_deterministic_and_balanced() -> None:
    values = [assign_variant("x", event.event_id) for event in events()]
    assert values == [assign_variant("x", event.event_id) for event in events()]
    assert 150 < values.count("control") < 350


def test_experiment_reports_metrics_and_reproducible_significance() -> None:
    first = run_experiment("x", events(), treatment_lift=0.12)
    second = run_experiment("x", events(), treatment_lift=0.12)
    assert first == second
    assert first.treatment.recovery_rate > first.control.recovery_rate
    assert first.treatment.recovered_revenue > first.control.recovered_revenue
    assert first.confidence_interval_95[0] <= first.recovery_rate_delta <= first.confidence_interval_95[1]


def test_what_if_is_a_projection_only() -> None:
    projection = project_what_if(events(), "six-hour-retry", 0.12)
    assert projection.projected_sample_size == 500
    assert projection.projected_recovery_rate > 0.5
