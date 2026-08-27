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
