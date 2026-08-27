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
