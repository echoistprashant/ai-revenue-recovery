from revenue_recovery.monitoring import ApplicationMetrics, drift_status, population_stability_index


def test_application_metrics_track_errors_and_latency() -> None:
    metrics = ApplicationMetrics()
    metrics.record(10, False)
    metrics.record(30, True)
    assert metrics.snapshot() == {"request_count": 2, "error_count": 1, "error_rate": 0.5, "average_latency_ms": 20.0}


def test_data_drift_is_detected() -> None:
    reference = ["CARD"] * 70 + ["UPI"] * 30
    shifted = ["CARD"] * 20 + ["UPI"] * 80
    psi = population_stability_index(reference, shifted)
    assert psi >= 0.25
    assert drift_status(psi) == "SIGNIFICANT_DRIFT"


def test_stable_population_is_not_flagged() -> None:
    population = ["CARD"] * 70 + ["UPI"] * 30
    assert drift_status(population_stability_index(population, population)) == "STABLE"
