from fastapi.testclient import TestClient

from revenue_recovery.api import create_app


def test_event_api_and_metrics(service, event_payload: dict) -> None:
    client = TestClient(create_app(service))
    response = client.post("/events", json=event_payload)
    assert response.status_code == 201
    assert response.json()["failure_category"] == "INSUFFICIENT_FUNDS"
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["total_failures"] == 1
    priorities = client.get("/priority-cases?limit=5")
    assert priorities.status_code == 200
    assert len(priorities.json()) == 1


def test_api_rejects_unknown_failure_code(service, event_payload: dict) -> None:
    event_payload["failure_code"] = "mystery_failure"
    response = TestClient(create_app(service)).post("/events", json=event_payload)
    assert response.status_code == 422
    assert "Unsupported failure code" in response.json()["detail"]


def test_recommendation_api_is_typed_and_personalized(service) -> None:
    response = TestClient(create_app(service)).post("/recommendations", json={
        "customer_id": "customer_1",
        "reference_hour": 10,
        "history": [
            {"customer_id": "customer_1", "timestamp": "2026-01-01T20:00:00Z", "payment_method": "UPI", "successful": True},
            {"customer_id": "customer_1", "timestamp": "2026-02-01T20:00:00Z", "payment_method": "UPI", "successful": True},
            {"customer_id": "customer_1", "timestamp": "2026-03-01T09:00:00Z", "payment_method": "CARD", "successful": False},
        ],
    })
    assert response.status_code == 200
    result = response.json()
    assert result["preferred_hour"] == 20
    assert result["retry_after_hours"] == 10
    assert result["recommended_payment_method"] == "UPI"


def test_decision_and_gateway_health_endpoints(service) -> None:
    client = TestClient(create_app(service))
    fraud = client.post("/decisions", json={
        "failure_category": "FRAUD_RISK_DECLINE", "amount": 100, "retry_count": 0,
        "recovery_probability": 0.99,
    })
    assert fraud.status_code == 200
    assert fraud.json()["action"] == "STOP_RECOVERY"
    incident = client.post("/gateway-health", json={
        "bank": "Bank", "gateway": "Gateway", "failures": 8, "total": 20,
    })
    assert incident.status_code == 200
    assert incident.json()["incident_active"] is True


def test_bounded_communication_and_analyst_endpoints(service, event_payload: dict) -> None:
    client = TestClient(create_app(service))
    client.post("/events", json=event_payload)
    communication = client.post("/communication", json={
        "action": "STOP_RECOVERY", "failure_category": "FRAUD_RISK_DECLINE", "amount": 100,
    })
    assert communication.status_code == 200
    assert communication.json()["action"] == "STOP_RECOVERY"
    analyst = client.post("/analyst", json={"question": "what is the recovery rate?"})
    assert analyst.status_code == 200
    assert "Source: get_recovery_metrics" in analyst.json()["answer"]


def test_experiment_endpoint_returns_typed_comparison(service) -> None:
    response = TestClient(create_app(service)).post("/experiments", json={
        "experiment_id": "exp-1",
        "events": [
            {"event_id": f"e-{i}", "amount": 100 + i, "latent_recovery_score": (i * 37 % 100) / 100}
            for i in range(20)
        ],
    })
    assert response.status_code == 200
    assert response.json()["control"]["sample_size"] + response.json()["treatment"]["sample_size"] == 20


def test_operational_metrics_and_drift_endpoints(service) -> None:
    client = TestClient(create_app(service))
    client.get("/health")
    metrics = client.get("/operational-metrics")
    assert metrics.status_code == 200
    assert metrics.json()["request_count"] >= 1
    assert metrics.json()["model_version"] == "recovery-logistic-v1"
    drift = client.post("/drift", json={
        "reference": ["CARD"] * 70 + ["UPI"] * 30,
        "current": ["CARD"] * 20 + ["UPI"] * 80,
    })
    assert drift.status_code == 200
    assert drift.json()["status"] == "SIGNIFICANT_DRIFT"


def test_history_endpoint_returns_event_log(service, event_payload: dict) -> None:
    client = TestClient(create_app(service))
    client.post("/events", json=event_payload)
    history = client.get("/history?limit=10")
    assert history.status_code == 200
    items = history.json()
    assert len(items) == 1
    assert items[0]["payment_id"] == event_payload["payment_id"]
    assert items[0]["failure_category"] == "INSUFFICIENT_FUNDS"
    assert items[0]["action"] is not None


def test_task_endpoints_report_and_drain_the_queue(queued_service, event_payload: dict) -> None:
    client = TestClient(create_app(queued_service))
    client.post("/events", json=event_payload)

    stats = client.get("/tasks/stats")
    assert stats.status_code == 200
    assert stats.json()["execution_mode"] == "queued"
    assert stats.json()["PENDING"] == 1

    # The scheduled retry is not due yet, so draining executes nothing.
    first = client.post("/tasks/run-due")
    assert first.status_code == 200
    assert first.json()["claimed"] == 0
    assert client.get("/tasks/stats").json()["PENDING"] == 1


def test_inline_mode_reports_an_empty_queue(service, event_payload: dict) -> None:
    client = TestClient(create_app(service))
    client.post("/events", json=event_payload)
    stats = client.get("/tasks/stats").json()
    assert stats["execution_mode"] == "inline"
    assert stats["PENDING"] == 0
    assert stats["DONE"] == 1
