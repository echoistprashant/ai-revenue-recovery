from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from revenue_recovery.api import create_app
from revenue_recovery.auth import Role, UserRepository
from revenue_recovery.config import QUEUED, Settings
from revenue_recovery.database import Database
from revenue_recovery.service import PaymentRecoveryService

MODEL_PATH = Path("models/recovery_model.joblib")

# Test credentials only. They exist in the test database for the duration of one test
# and are never a default anywhere in the application.
TEST_PASSWORD = "test-password-1234"
SIGNING_KEY = "test-signing-key-that-is-long-enough-for-production"


@pytest.fixture
def service(tmp_path: Path) -> PaymentRecoveryService:
    settings = Settings(
        database_path=tmp_path / "test.db",
        recovery_model_path=MODEL_PATH,
    )
    return PaymentRecoveryService(Database(settings.database_path), settings)


@pytest.fixture
def queued_service(tmp_path: Path) -> PaymentRecoveryService:
    """Same service with background execution, for durable-queue tests."""
    settings = Settings(
        database_path=tmp_path / "queued.db",
        recovery_model_path=MODEL_PATH,
        task_execution_mode=QUEUED,
    )
    return PaymentRecoveryService(Database(settings.database_path), settings)


def build_client(
    service: PaymentRecoveryService,
    role: Role = Role.ADMIN,
    username: str = "tester",
    tenant_id: str | None = None,
) -> TestClient:
    """An app plus one account, with the client pre-authenticated as that account.

    Every route except ``/health``, ``/auth/token``, and the signed webhook needs a
    token, so tests that exercise business behaviour get one here instead of
    repeating the login call. Tests about authentication itself build their own
    unauthenticated clients.
    """
    app = create_app(service, signing_key=SIGNING_KEY)
    users: UserRepository = app.state.users
    tenant = tenant_id or service.settings.default_tenant
    users.create(username, TEST_PASSWORD, role, tenant)
    client = TestClient(app)
    token = client.post("/auth/token", json={"username": username, "password": TEST_PASSWORD})
    assert token.status_code == 200, token.text
    client.headers["Authorization"] = f"Bearer {token.json()['access_token']}"
    return client


@pytest.fixture
def client(service: PaymentRecoveryService) -> TestClient:
    """Admin-authenticated client against the inline-mode service."""
    return build_client(service)


@pytest.fixture
def queued_client(queued_service: PaymentRecoveryService) -> TestClient:
    """Admin-authenticated client against the queued-mode service."""
    return build_client(queued_service)


@pytest.fixture
def event_payload() -> dict:
    return {
        "payment_id": "pay_001",
        "attempt_id": "attempt_001",
        "customer_id": "customer_001",
        "subscription_id": "subscription_001",
        "amount": 1499.0,
        "currency": "INR",
        "payment_method": "CARD",
        "gateway": "synthetic_gateway",
        "bank": "Example Bank",
        "failure_code": "insufficient_funds",
        "timestamp": "2026-08-27T10:00:00+05:30",
        "previous_success_count": 8,
        "previous_failure_count": 1,
        "customer_age_days": 365,
        "subscription_value": 1499.0,
        "retry_count": 0,
    }
