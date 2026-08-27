from pathlib import Path

import pytest

from revenue_recovery.config import QUEUED, Settings
from revenue_recovery.database import Database
from revenue_recovery.service import PaymentRecoveryService

MODEL_PATH = Path("models/recovery_model.joblib")


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
