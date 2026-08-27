import pytest
from fastapi.testclient import TestClient

from dashboard.api_client import APIClient, APIClientError
from revenue_recovery.api import create_app


def test_api_client_success_methods(service, event_payload: dict) -> None:
    # Use FastAPI TestClient to test client logic by mocking requests.request
    client = TestClient(create_app(service))
    
    api = APIClient(base_url="http://testserver")
    
    # Patch request method on requests to route to testclient
    def mock_request(method, url, timeout=None, **kwargs):
        path = url.replace("http://testserver", "")
        return client.request(method, path, **kwargs)

    import requests
    original_request = requests.request
    requests.request = mock_request
    try:
        health = api.get_health()
        assert health["status"] == "ok"

        event_res = api.ingest_event(event_payload)
        assert event_res["failure_category"] == "INSUFFICIENT_FUNDS"

        metrics = api.get_metrics()
        assert metrics["total_failures"] >= 1

        op_metrics = api.get_operational_metrics()
        assert "model_version" in op_metrics

        priority = api.get_priority_cases(5)
        assert isinstance(priority, list)

        history = api.get_history(5)
        assert len(history) >= 1

        comm = api.generate_communication({
            "action": "STOP_RECOVERY",
            "failure_category": "FRAUD_RISK_DECLINE",
            "amount": 500,
        })
        assert "message" in comm

        analyst = api.ask_analyst("What is the recovery rate?")
        assert "answer" in analyst

        task_stats = api.get_task_stats()
        assert task_stats["execution_mode"] == "inline"

        drained = api.run_due_tasks()
        assert drained["claimed"] == 0
    finally:
        requests.request = original_request


def test_api_client_error_handling() -> None:
    api = APIClient(base_url="http://127.0.0.1:59999", timeout=0.2)  # Invalid port
    with pytest.raises(APIClientError) as exc_info:
        api.get_health()
    err_str = str(exc_info.value)
    assert "Could not connect" in err_str or "timed out" in err_str

