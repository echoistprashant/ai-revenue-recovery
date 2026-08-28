"""Tests for the dashboard's HTTP client.

The client is exercised against a real app through ``requests.request``, so the
assertions here cover the wire contract the dashboard depends on — including the
fact that an unauthenticated call is reported as "log in again" rather than as a
backend failure.
"""

import pytest
from fastapi.testclient import TestClient

from conftest import SIGNING_KEY, TEST_PASSWORD
from dashboard.api_client import APIClient, APIClientError, AuthenticationRequiredError
from revenue_recovery.api import create_app
from revenue_recovery.auth import Role


def route_to(client: TestClient):
    """A ``requests.request`` stand-in that sends the call into a TestClient."""

    def mock_request(method, url, timeout=None, **kwargs):
        path = url.replace("http://testserver", "")
        return client.request(method, path, **kwargs)

    return mock_request


def test_api_client_success_methods(service, event_payload: dict, monkeypatch) -> None:
    app = create_app(service, signing_key=SIGNING_KEY)
    app.state.users.create("dash-admin", TEST_PASSWORD, Role.ADMIN, service.settings.default_tenant)
    client = TestClient(app)

    api = APIClient(base_url="http://testserver")
    monkeypatch.setattr("requests.request", route_to(client))

    health = api.get_health()
    assert health["status"] == "ok"

    session = api.login("dash-admin", TEST_PASSWORD)
    assert session["role"] == "ADMIN"
    assert api.token

    me = api.whoami()
    assert me["username"] == "dash-admin"
    assert me["tenant_id"] == service.settings.default_tenant

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

    audit = api.get_audit_log(event_id=event_res["event_id"])
    assert audit and all(entry["event_id"] == event_res["event_id"] for entry in audit)

    assert isinstance(api.get_review_queue(), list)

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

    users = api.list_users()
    assert [item["username"] for item in users] == ["dash-admin"]

    created = api.create_user({
        "username": "dash-viewer",
        "password": TEST_PASSWORD,
        "role": "VIEWER",
    })
    assert created["role"] == "VIEWER"
    assert "password" not in created

    deactivated = api.deactivate_user("dash-viewer")
    assert deactivated["is_active"] is False

    api.logout()
    assert api.token is None


def test_api_client_reports_missing_token_as_authentication_required(service, monkeypatch) -> None:
    """A tokenless business call must be distinguishable from an outage.

    The dashboard shows the login form for this error, so misclassifying it would
    strand the operator on a "backend is down" screen they cannot act on.
    """
    client = TestClient(create_app(service, signing_key=SIGNING_KEY))
    api = APIClient(base_url="http://testserver")
    monkeypatch.setattr("requests.request", route_to(client))

    with pytest.raises(AuthenticationRequiredError):
        api.get_metrics()


def test_api_client_reports_forbidden_role_as_plain_error(service, monkeypatch) -> None:
    """A 403 is a real answer from the backend, not a broken session.

    Re-prompting for a password would be the wrong response: the credentials are
    fine, the role is simply not high enough.
    """
    app = create_app(service, signing_key=SIGNING_KEY)
    app.state.users.create("dash-readonly", TEST_PASSWORD, Role.VIEWER, service.settings.default_tenant)
    client = TestClient(app)

    api = APIClient(base_url="http://testserver")
    monkeypatch.setattr("requests.request", route_to(client))
    api.login("dash-readonly", TEST_PASSWORD)

    with pytest.raises(APIClientError) as exc_info:
        api.list_users()
    assert not isinstance(exc_info.value, AuthenticationRequiredError)
    assert "403" in str(exc_info.value)


def test_api_client_error_handling() -> None:
    api = APIClient(base_url="http://127.0.0.1:59999", timeout=0.2)  # Invalid port
    with pytest.raises(APIClientError) as exc_info:
        api.get_health()
    err_str = str(exc_info.value)
    assert "Could not connect" in err_str or "timed out" in err_str
