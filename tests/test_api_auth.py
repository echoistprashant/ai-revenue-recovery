"""Authentication, authorization, and tenant isolation at the HTTP boundary.

These are the tests that would have to fail before the platform could be reached by
someone who should not reach it. They cover four separate questions:

1. Can a request without a valid token reach anything that matters?
2. Can a valid token reach something above its role?
3. Can one tenant see or touch another tenant's data?
4. Does any of the above change what the decision engine will approve?

The answer to the fourth is the important one: a role widens which routes a request
may reach, and nothing more. The fraud hard stop is tested from every role.
"""

from datetime import timedelta
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from conftest import MODEL_PATH, SIGNING_KEY, TEST_PASSWORD, build_client
from revenue_recovery.api import create_app
from revenue_recovery.auth import Role, UserRepository
from revenue_recovery.config import Settings
from revenue_recovery.database import Database
from revenue_recovery.service import PaymentRecoveryService

# Routes that must refuse an anonymous caller, with the method each is reached by.
PROTECTED_ROUTES = [
    ("GET", "/auth/me"),
    ("GET", "/auth/users"),
    ("GET", "/metrics"),
    ("GET", "/priority-cases"),
    ("GET", "/history"),
    ("GET", "/audit-log"),
    ("GET", "/review-queue"),
    ("GET", "/operational-metrics"),
    ("GET", "/tasks/stats"),
    ("POST", "/events"),
    ("POST", "/communication"),
    ("POST", "/analyst"),
    ("POST", "/decisions"),
    ("POST", "/tasks/run-due"),
    ("POST", "/review-queue/1/resolve"),
]


def anonymous(service: PaymentRecoveryService) -> TestClient:
    """A client with no credentials at all."""
    return TestClient(create_app(service, signing_key=SIGNING_KEY))


def fraud_event(payload: dict) -> dict:
    return payload | {
        "payment_id": "pay_fraud",
        "attempt_id": "attempt_fraud",
        "failure_code": "fraud_suspected",
    }


# --------------------------------------------------------------------------- #
# 1. Requests without a usable token
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
def test_every_business_route_refuses_an_anonymous_caller(service, method: str, path: str) -> None:
    response = anonymous(service).request(method, path, json={})
    assert response.status_code == 401, f"{method} {path} returned {response.status_code}"
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_health_stays_open(service) -> None:
    """Load balancers cannot present a token, so ``/health`` must not need one."""
    assert anonymous(service).get("/health").status_code == 200


@pytest.mark.parametrize(
    "header",
    [
        "",
        "Bearer",
        "Bearer ",
        "Basic dXNlcjpwYXNz",
        "token abc.def.ghi",
        "bearer-not-a-scheme",
    ],
)
def test_malformed_authorization_headers_are_refused(service, header: str) -> None:
    response = anonymous(service).get("/metrics", headers={"Authorization": header})
    assert response.status_code == 401


def test_a_token_signed_with_another_key_is_refused(service) -> None:
    """The forged token is well formed and claims ADMIN; only the signature is wrong."""
    app = create_app(service, signing_key=SIGNING_KEY)
    app.state.users.create("real-admin", TEST_PASSWORD, Role.ADMIN, service.settings.default_tenant)
    forged = jwt.encode(
        {"sub": "real-admin", "role": "ADMIN", "tenant": "default", "iat": 0, "exp": 9_999_999_999},
        "an-entirely-different-signing-key!!",
        algorithm="HS256",
    )
    response = TestClient(app).get("/auth/users", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_an_unsigned_token_is_refused(service) -> None:
    """``alg: none`` must not be accepted as "already verified"."""
    app = create_app(service, signing_key=SIGNING_KEY)
    app.state.users.create("real-admin", TEST_PASSWORD, Role.ADMIN, service.settings.default_tenant)
    forged = jwt.encode(
        {"sub": "real-admin", "role": "ADMIN", "tenant": "default", "iat": 0, "exp": 9_999_999_999},
        key="",
        algorithm="none",
    )
    response = TestClient(app).get("/auth/users", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_a_tampered_token_is_refused(service) -> None:
    client = build_client(service)
    good = client.headers["Authorization"].removeprefix("Bearer ")
    header, payload, signature = good.split(".")
    client.headers["Authorization"] = f"Bearer {header}.{payload}.{signature[:-2]}xy"
    assert client.get("/metrics").status_code == 401


def test_an_expired_token_is_refused(service) -> None:
    app = create_app(service, signing_key=SIGNING_KEY)
    app.state.users.create("tester", TEST_PASSWORD, Role.ADMIN, service.settings.default_tenant)
    app.state.signer.ttl = timedelta(seconds=-1)
    client = TestClient(app)
    token = client.post("/auth/token", json={"username": "tester", "password": TEST_PASSWORD})
    assert token.status_code == 200
    expired = token.json()["access_token"]
    assert client.get("/metrics", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_login_does_not_reveal_which_usernames_exist(service) -> None:
    app = create_app(service, signing_key=SIGNING_KEY)
    app.state.users.create("known", TEST_PASSWORD, Role.VIEWER, service.settings.default_tenant)
    client = TestClient(app)
    wrong_password = client.post("/auth/token", json={"username": "known", "password": "wrong-password-here"})
    unknown_user = client.post("/auth/token", json={"username": "ghost", "password": "wrong-password-here"})
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json()["detail"] == unknown_user.json()["detail"]


def test_deactivating_an_account_invalidates_its_live_token(service) -> None:
    """Revocation must not wait for the token to expire.

    The role and active flag are re-read from the ``users`` row on every request, so
    the token issued a moment ago stops working immediately.
    """
    client = build_client(service, role=Role.VIEWER, username="soon-gone")
    assert client.get("/metrics").status_code == 200
    UserRepository(service.database).set_active("soon-gone", False)
    response = client.get("/metrics")
    assert response.status_code == 401
    assert "deactivated" in response.json()["detail"].lower()


def test_demoting_an_account_takes_effect_without_a_new_login(service, event_payload: dict) -> None:
    """A token minted while the account was an operator must not keep operator reach."""
    client = build_client(service, role=Role.OPERATOR, username="demoted")
    assert client.post("/events", json=event_payload).status_code == 201
    with service.database.connect() as connection:
        connection.execute("UPDATE users SET role = 'VIEWER' WHERE username = 'demoted'")
    second = event_payload | {"attempt_id": "attempt_002"}
    assert client.post("/events", json=second).status_code == 403


# --------------------------------------------------------------------------- #
# 2. Role boundaries
# --------------------------------------------------------------------------- #


VIEWER_FORBIDDEN = [
    ("POST", "/events"),
    ("POST", "/communication"),
    ("POST", "/tasks/run-due"),
    ("POST", "/review-queue/1/resolve"),
]

OPERATOR_FORBIDDEN = [
    ("GET", "/auth/users"),
    ("POST", "/auth/users"),
    ("POST", "/auth/users/someone/deactivate"),
]


@pytest.mark.parametrize("method,path", VIEWER_FORBIDDEN)
def test_a_viewer_cannot_reach_operator_routes(service, method: str, path: str) -> None:
    client = build_client(service, role=Role.VIEWER, username="read-only")
    response = client.request(method, path, json={})
    assert response.status_code == 403
    assert "OPERATOR" in response.json()["detail"]


@pytest.mark.parametrize("method,path", OPERATOR_FORBIDDEN)
def test_an_operator_cannot_reach_admin_routes(service, method: str, path: str) -> None:
    client = build_client(service, role=Role.OPERATOR, username="op")
    response = client.request(method, path, json={})
    assert response.status_code == 403
    assert "ADMIN" in response.json()["detail"]


def test_a_viewer_can_read_dashboards_and_the_review_queue(service) -> None:
    client = build_client(service, role=Role.VIEWER, username="read-only")
    for path in ("/metrics", "/history", "/priority-cases", "/audit-log", "/review-queue", "/tasks/stats"):
        assert client.get(path).status_code == 200, path


def test_an_operator_inherits_viewer_reach(service, event_payload: dict) -> None:
    client = build_client(service, role=Role.OPERATOR, username="op")
    assert client.get("/metrics").status_code == 200
    assert client.post("/events", json=event_payload).status_code == 201


def test_whoami_reports_the_signed_in_account(service) -> None:
    client = build_client(service, role=Role.OPERATOR, username="op", tenant_id="acme")
    body = client.get("/auth/me").json()
    assert body["username"] == "op"
    assert body["role"] == "OPERATOR"
    assert body["tenant_id"] == "acme"
    assert "password" not in body and "password_hash" not in body


def test_an_admin_cannot_deactivate_their_own_account(service) -> None:
    """Locking the last administrator out would need database access to undo."""
    client = build_client(service, role=Role.ADMIN, username="boss")
    response = client.post("/auth/users/boss/deactivate")
    assert response.status_code == 422


def test_created_accounts_land_in_the_creating_admins_tenant(service) -> None:
    """A tenant field in the request body must not be able to plant an account
    elsewhere; holding one tenant's admin password is not reach into another."""
    client = build_client(service, role=Role.ADMIN, username="boss", tenant_id="acme")
    created = client.post("/auth/users", json={
        "username": "smuggled",
        "password": TEST_PASSWORD,
        "role": "ADMIN",
        "tenant_id": "globex",
    })
    assert created.status_code == 201
    assert created.json()["tenant_id"] == "acme"


def test_creating_a_duplicate_account_conflicts(service) -> None:
    client = build_client(service, role=Role.ADMIN, username="boss")
    payload = {"username": "twin", "password": TEST_PASSWORD, "role": "VIEWER"}
    assert client.post("/auth/users", json=payload).status_code == 201
    assert client.post("/auth/users", json=payload).status_code == 409


def test_a_weak_password_is_refused_at_the_api(service) -> None:
    client = build_client(service, role=Role.ADMIN, username="weak-maker")
    response = client.post("/auth/users", json={"username": "weak", "password": "short", "role": "VIEWER"})
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# 3. Tenant isolation
# --------------------------------------------------------------------------- #


@pytest.fixture
def two_tenants(service) -> tuple[TestClient, TestClient]:
    """Two admin clients on one database, in different tenants."""
    acme = build_client(service, role=Role.ADMIN, username="acme-admin", tenant_id="acme")
    globex = build_client(service, role=Role.ADMIN, username="globex-admin", tenant_id="globex")
    return acme, globex


def test_reads_are_scoped_to_the_callers_tenant(two_tenants, event_payload: dict) -> None:
    acme, globex = two_tenants
    assert acme.post("/events", json=event_payload).status_code == 201

    assert acme.get("/metrics").json()["total_failures"] == 1
    assert globex.get("/metrics").json()["total_failures"] == 0
    assert len(acme.get("/history").json()) == 1
    assert globex.get("/history").json() == []
    assert globex.get("/priority-cases").json() == []


def test_the_same_gateway_identifier_can_exist_in_two_tenants(two_tenants, event_payload: dict) -> None:
    """The idempotency key is ``(tenant, payment, attempt)``.

    A global key would reject the second tenant's genuinely different payment and, in
    doing so, tell it that another tenant holds that identifier.
    """
    acme, globex = two_tenants
    first = acme.post("/events", json=event_payload)
    second = globex.post("/events", json=event_payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["event_id"] != second.json()["event_id"]
    assert acme.get("/metrics").json()["total_failures"] == 1
    assert globex.get("/metrics").json()["total_failures"] == 1


def test_a_duplicate_within_one_tenant_is_still_deduplicated(two_tenants, event_payload: dict) -> None:
    acme, _ = two_tenants
    first = acme.post("/events", json=event_payload)
    second = acme.post("/events", json=event_payload)
    assert first.json()["event_id"] == second.json()["event_id"]
    assert acme.get("/metrics").json()["total_failures"] == 1


def test_the_audit_trail_does_not_cross_tenants(two_tenants, event_payload: dict) -> None:
    """Asking for another tenant's event id must return nothing, not its history."""
    acme, globex = two_tenants
    event_id = acme.post("/events", json=event_payload).json()["event_id"]
    assert acme.get("/audit-log", params={"event_id": event_id}).json()
    assert globex.get("/audit-log", params={"event_id": event_id}).json() == []


def test_the_review_queue_does_not_cross_tenants(two_tenants, event_payload: dict) -> None:
    acme, globex = two_tenants
    high_value = event_payload | {"amount": 60000.0, "subscription_value": 60000.0}
    acme.post("/events", json=high_value)
    assert len(acme.get("/review-queue").json()) == 1
    assert globex.get("/review-queue").json() == []


def test_resolving_another_tenants_case_reports_it_as_missing(two_tenants, event_payload: dict) -> None:
    """404 rather than 403: a 403 would confirm the case exists."""
    acme, globex = two_tenants
    high_value = event_payload | {"amount": 60000.0, "subscription_value": 60000.0}
    event_id = acme.post("/events", json=high_value).json()["event_id"]
    response = globex.post(f"/review-queue/{event_id}/resolve", json={"resolution": "WRITTEN_OFF"})
    assert response.status_code == 404


def test_account_listings_and_deactivation_do_not_cross_tenants(two_tenants) -> None:
    acme, globex = two_tenants
    assert [user["username"] for user in acme.get("/auth/users").json()] == ["acme-admin"]
    assert [user["username"] for user in globex.get("/auth/users").json()] == ["globex-admin"]
    assert globex.post("/auth/users/acme-admin/deactivate").status_code == 404


def test_the_analyst_only_sees_its_own_tenants_numbers(two_tenants, event_payload: dict) -> None:
    """The read-only tools handed to the LLM are bound to the caller's tenant, so a
    question cannot be phrased to reach across the boundary."""
    acme, globex = two_tenants
    acme.post("/events", json=event_payload)
    question = {"question": "How many failures are there in total?"}
    assert "INSUFFICIENT_FUNDS" in acme.post("/analyst", json=question).json()["answer"]
    assert "INSUFFICIENT_FUNDS" not in globex.post("/analyst", json=question).json()["answer"]


# --------------------------------------------------------------------------- #
# 4. Rate limiting and transport
# --------------------------------------------------------------------------- #


def limited_service(tmp_path: Path, **overrides) -> PaymentRecoveryService:
    settings = Settings(
        database_path=tmp_path / "limited.db",
        recovery_model_path=MODEL_PATH,
        **overrides,
    )
    return PaymentRecoveryService(Database(settings.database_path), settings)


def test_requests_past_the_limit_get_429_with_retry_after(tmp_path: Path) -> None:
    client = TestClient(create_app(limited_service(tmp_path, rate_limit_per_minute=3), signing_key=SIGNING_KEY))
    assert [client.get("/health").status_code for _ in range(3)] == [200, 200, 200]
    blocked = client.get("/health")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_login_attempts_have_their_own_tighter_limit(tmp_path: Path) -> None:
    """Guessing passwords must run out of attempts long before ordinary API traffic
    runs out of requests."""
    app = create_app(
        limited_service(tmp_path, rate_limit_per_minute=100, login_rate_limit_per_minute=2),
        signing_key=SIGNING_KEY,
    )
    app.state.users.create("target", TEST_PASSWORD, Role.ADMIN, "default")
    client = TestClient(app)
    guess = {"username": "target", "password": "not-the-password"}
    assert client.post("/auth/token", json=guess).status_code == 401
    assert client.post("/auth/token", json=guess).status_code == 401
    throttled = client.post("/auth/token", json=guess)
    assert throttled.status_code == 429
    assert "Retry-After" in throttled.headers


def test_a_throttled_login_stays_closed_even_with_the_right_password(tmp_path: Path) -> None:
    """The limit is on attempts, not on failures, so an attacker cannot spend the
    budget guessing and then slip a correct password through."""
    app = create_app(
        limited_service(tmp_path, rate_limit_per_minute=100, login_rate_limit_per_minute=1),
        signing_key=SIGNING_KEY,
    )
    app.state.users.create("target", TEST_PASSWORD, Role.ADMIN, "default")
    client = TestClient(app)
    client.post("/auth/token", json={"username": "target", "password": "wrong-password-here"})
    assert client.post("/auth/token", json={"username": "target", "password": TEST_PASSWORD}).status_code == 429


def test_plain_http_is_refused_when_https_is_enforced(tmp_path: Path) -> None:
    """403, not a redirect: a redirect would already have carried the token in clear."""
    client = TestClient(create_app(limited_service(tmp_path, enforce_https=True), signing_key=SIGNING_KEY))
    response = client.get("/health")
    assert response.status_code == 403
    assert "HTTPS" in response.json()["detail"]


def test_a_terminated_tls_request_is_accepted_when_https_is_enforced(tmp_path: Path) -> None:
    """The proxy terminates TLS and forwards the original scheme."""
    client = TestClient(create_app(limited_service(tmp_path, enforce_https=True), signing_key=SIGNING_KEY))
    assert client.get("/health", headers={"X-Forwarded-Proto": "https"}).status_code == 200


def test_https_is_not_enforced_by_default(tmp_path: Path) -> None:
    client = TestClient(create_app(limited_service(tmp_path), signing_key=SIGNING_KEY))
    assert client.get("/health").status_code == 200


# --------------------------------------------------------------------------- #
# 5. Roles do not widen what the decision engine approves
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.ADMIN])
def test_a_fraud_decline_is_stopped_no_matter_who_ingests_it(service, event_payload: dict, role: Role) -> None:
    client = build_client(service, role=role, username=f"{role.value.lower()}-ingestor")
    body = client.post("/events", json=fraud_event(event_payload)).json()
    assert body["failure_category"] == "FRAUD_RISK_DECLINE"
    assert body["action"] == "STOP_RECOVERY"
    assert "Fraud-risk declines cannot be automatically recovered." in body["reason"]
    assert body["recovered"] is None
    assert client.get("/history").json()[0]["final_state"] == "STOPPED"


@pytest.mark.parametrize("role", [Role.VIEWER, Role.OPERATOR, Role.ADMIN])
def test_no_role_gets_a_different_answer_from_the_decision_engine(service, role: Role) -> None:
    """The engine is deterministic and takes no account of who is asking."""
    client = build_client(service, role=role, username=f"{role.value.lower()}-asker")
    response = client.post("/decisions", json={
        "failure_category": "FRAUD_RISK_DECLINE",
        "amount": 1000.0,
        "retry_count": 0,
        "recovery_probability": 0.99,
    })
    assert response.json()["action"] == "STOP_RECOVERY"
    assert response.json()["guardrail_rule"] == "FRAUD_HARD_STOP"


def test_a_fraud_case_never_enters_the_review_queue(service, event_payload: dict) -> None:
    """The first of the two barriers: a stopped case is not offered to a reviewer."""
    client = build_client(service, role=Role.ADMIN, username="reviewer")
    client.post("/events", json=fraud_event(event_payload))
    assert client.get("/review-queue").json() == []


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.ADMIN])
def test_a_fraud_case_cannot_be_resolved_into_a_retry(service, event_payload: dict, role: Role) -> None:
    """The second barrier. An operator who knows the event id still cannot retry it:
    the case is not in a reviewable state, so the request is refused outright."""
    client = build_client(service, role=role, username=f"{role.value.lower()}-resolver")
    event_id = client.post("/events", json=fraud_event(event_payload)).json()["event_id"]
    response = client.post(f"/review-queue/{event_id}/resolve", json={"resolution": "MANUAL_RETRY"})
    assert response.status_code == 409
    assert "STOPPED" in response.json()["detail"]


def test_a_high_value_case_can_be_retried_by_a_reviewer(service, event_payload: dict) -> None:
    """The counterpart: the guardrail that exists to wait for a person is cleared by
    one, so the queue can actually be worked. This is the only route in the system
    that turns a human decision into a payment attempt, and it still goes through the
    engine."""
    client = build_client(service, role=Role.OPERATOR, username="queue-worker")
    high_value = event_payload | {"amount": 60000.0, "subscription_value": 60000.0}
    ingested = client.post("/events", json=high_value).json()
    assert ingested["action"] == "ESCALATE_TO_HUMAN"
    queued = client.get("/review-queue").json()
    assert [case["event_id"] for case in queued] == [ingested["event_id"]]
    assert queued[0]["final_state"] == "ESCALATED"

    resolved = client.post(
        f"/review-queue/{ingested['event_id']}/resolve",
        json={"resolution": "MANUAL_RETRY", "note": "Verified with the customer by phone"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["executed"] is True
    assert resolved.json()["resolved_by"] == "queue-worker"
    assert client.get("/review-queue").json() == []


def test_a_resolution_is_recorded_in_the_audit_trail(service, event_payload: dict) -> None:
    """Who closed a case, how, and why has to survive in the record."""
    client = build_client(service, role=Role.OPERATOR, username="queue-worker")
    high_value = event_payload | {"amount": 60000.0, "subscription_value": 60000.0}
    event_id = client.post("/events", json=high_value).json()["event_id"]
    client.post(f"/review-queue/{event_id}/resolve", json={"resolution": "WRITTEN_OFF", "note": "Customer churned"})

    trail = client.get("/audit-log", params={"event_id": event_id}).json()
    resolutions = [entry for entry in trail if entry["event_type"] == "CASE_RESOLVED"]
    assert len(resolutions) == 1
    assert resolutions[0]["details"]["resolved_by"] == "queue-worker"
    assert resolutions[0]["details"]["resolution"] == "WRITTEN_OFF"
    assert resolutions[0]["details"]["note"] == "Customer churned"


def test_a_case_cannot_be_resolved_twice(service, event_payload: dict) -> None:
    """Otherwise the same recovery could be counted more than once."""
    client = build_client(service, role=Role.OPERATOR, username="queue-worker")
    high_value = event_payload | {"amount": 60000.0, "subscription_value": 60000.0}
    event_id = client.post("/events", json=high_value).json()["event_id"]
    first = client.post(f"/review-queue/{event_id}/resolve", json={"resolution": "MANUAL_RECOVERED"})
    second = client.post(f"/review-queue/{event_id}/resolve", json={"resolution": "MANUAL_RECOVERED"})
    assert first.status_code == 200
    assert second.status_code == 409


def test_an_approved_retry_can_still_be_withheld_by_the_engine(service, event_payload: dict) -> None:
    """Approval is permission to ask the engine again, not permission to retry.

    This customer's score does not justify an automated attempt, so the engine
    withholds it at execution time. The case stays open rather than being closed as
    handled, and nothing is recorded as recovered.
    """
    client = build_client(service, role=Role.OPERATOR, username="queue-worker")
    unlikely = event_payload | {
        "amount": 60000.0,
        "subscription_value": 60000.0,
        "failure_code": "invalid_card",
        "previous_success_count": 0,
        "previous_failure_count": 9,
        "customer_age_days": 10,
    }
    event_id = client.post("/events", json=unlikely).json()["event_id"]
    resolved = client.post(f"/review-queue/{event_id}/resolve", json={"resolution": "MANUAL_RETRY"})

    assert resolved.status_code == 200
    assert resolved.json()["executed"] is False
    assert resolved.json()["recovered"] is None
    assert "withheld" in resolved.json()["detail"].lower()
    assert [case["event_id"] for case in client.get("/review-queue").json()] == [event_id]
    assert client.get("/metrics").json()["recovered_events"] == 0


def test_the_communication_route_cannot_be_used_to_trigger_an_action(service) -> None:
    """The LLM writes copy for an action someone else already approved. Asking it for
    a fraud-decline message returns text and nothing else — no decision, no side
    effect, and the case's own state is untouched."""
    client = build_client(service, role=Role.OPERATOR, username="writer")
    response = client.post("/communication", json={
        "action": "STOP_RECOVERY",
        "failure_category": "FRAUD_RISK_DECLINE",
        "amount": 500.0,
    })
    assert response.status_code == 200
    assert response.json()["action"] == "STOP_RECOVERY"
    assert client.get("/metrics").json()["total_failures"] == 0

