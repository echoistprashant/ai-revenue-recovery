"""Tests for live Razorpay adapter and outbound retry provider safety invariants."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from revenue_recovery.actions import ActionContext, ActionExecutor, RazorpayRetryProvider, SimulatedRetryProvider
from revenue_recovery.adapters.razorpay import RazorpayAdapter
from revenue_recovery.api import create_app
from revenue_recovery.config import Settings
from revenue_recovery.database import Database
from revenue_recovery.models import FailureCategory, RecoveryAction
from revenue_recovery.service import PaymentRecoveryService


def test_fraud_risk_decline_never_calls_razorpay_api():
    """Safety invariant: FRAUD_RISK_DECLINE must NEVER trigger an outbound API call to Razorpay."""
    provider = RazorpayRetryProvider(key_id="rzp_test_mock", key_secret="mock_secret")
    context = ActionContext(
        event_id=101,
        payment_id="pay_fraud_test_123",
        category=FailureCategory.FRAUD_RISK_DECLINE,
        amount=5000.0,
        retry_count=0,
        recovery_probability=0.9,
    )

    with patch("requests.post") as mock_post:
        success = provider.attempt_retry(context)
        assert success is False
        mock_post.assert_not_called()


def test_action_executor_with_fraud_hard_stop_never_calls_retry_provider():
    """ActionExecutor re-validates guardrails and denies retry for fraud cases."""
    mock_retry_provider = MagicMock()
    executor = ActionExecutor(retry_provider=mock_retry_provider)
    context = ActionContext(
        event_id=102,
        payment_id="pay_fraud_test_456",
        category=FailureCategory.FRAUD_RISK_DECLINE,
        amount=100.0,
        retry_count=0,
        recovery_probability=0.9,
    )

    from revenue_recovery.tasks import TaskType
    result = executor.execute(TaskType.EXECUTE_RETRY, context)

    assert result.executed is False
    assert result.revalidated_action is RecoveryAction.STOP_RECOVERY
    mock_retry_provider.attempt_retry.assert_not_called()


def test_provider_selection_based_on_credentials(tmp_path):
    """PaymentRecoveryService selects RazorpayRetryProvider iff credentials are provided."""
    db_path = tmp_path / "test.db"
    
    # Without credentials
    settings_no_creds = Settings(database_path=db_path, razorpay_key_id="", razorpay_key_secret="")
    service_simulated = PaymentRecoveryService(Database(db_path), settings_no_creds)
    assert isinstance(service_simulated.action_executor.retry_provider, SimulatedRetryProvider)

    # With credentials
    settings_creds = Settings(
        database_path=db_path,
        razorpay_key_id="rzp_test_123",
        razorpay_key_secret="secret_123",
    )
    service_real = PaymentRecoveryService(Database(db_path), settings_creds)
    assert isinstance(service_real.action_executor.retry_provider, RazorpayRetryProvider)


def test_razorpay_retry_provider_handles_api_success():
    """RazorpayRetryProvider correctly parses successful order response (200/201)."""
    provider = RazorpayRetryProvider(key_id="rzp_test_123", key_secret="secret_123")
    context = ActionContext(
        event_id=201,
        payment_id="pay_insufficient_123",
        category=FailureCategory.INSUFFICIENT_FUNDS,
        amount=1499.0,
        retry_count=0,
        recovery_probability=0.85,
    )

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"id": "order_123", "status": "created"}

    with patch("requests.post", return_value=mock_response) as mock_post:
        success = provider.attempt_retry(context)
        assert success is True
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["auth"] == ("rzp_test_123", "secret_123")
        assert kwargs["json"]["amount"] == 149900


def test_razorpay_retry_provider_handles_api_failure_gracefully():
    """RazorpayRetryProvider logs warning and returns False when API raises exception."""
    provider = RazorpayRetryProvider(key_id="rzp_test_123", key_secret="secret_123")
    context = ActionContext(
        event_id=202,
        payment_id="pay_insufficient_456",
        category=FailureCategory.INSUFFICIENT_FUNDS,
        amount=1499.0,
        retry_count=0,
        recovery_probability=0.85,
    )

    with patch("requests.post", side_effect=Exception("Network timeout")):
        success = provider.attempt_retry(context)
        assert success is False


def test_real_webhook_payload_ingestion_end_to_end(tmp_path):
    """Simulates real Razorpay webhook payload arriving at POST /webhooks/razorpay."""
    db_path = tmp_path / "webhook_test.db"
    webhook_secret = "test_secret_key_12345678901234567890"
    settings = Settings(
        database_path=db_path,
        razorpay_webhook_secret=webhook_secret,
        environment="development",
    )
    db = Database(db_path)
    service = PaymentRecoveryService(db, settings)
    app = create_app(service=service, settings=settings)
    client = TestClient(app)

    now_ts = int(datetime.now(timezone.utc).timestamp())

    payload = {
        "entity": "event",
        "account_id": "acc_test_rzp_01",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_live_test_999",
                    "entity": "payment",
                    "amount": 299900,
                    "currency": "INR",
                    "status": "failed",
                    "method": "card",
                    "bank": "HDFC",
                    "error_code": "BAD_REQUEST_PAYMENT_ACCOUNT_INSUFFICIENT_BALANCE",
                    "error_description": "Payment failed due to insufficient funds.",
                    "notes": {
                        "customer_id": "cust_live_123",
                        "subscription_id": "sub_live_456",
                        "attempt_id": "att_live_1",
                        "previous_success_count": 5,
                        "previous_failure_count": 0,
                        "customer_age_days": 180,
                        "subscription_value": 2999.0,
                        "retry_count": 0,
                    },
                    "created_at": now_ts,
                }
            }
        },
        "created_at": now_ts,
    }

    body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    
    import hashlib
    import hmac
    signature = hmac.new(webhook_secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhooks/razorpay",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
        },
    )

    assert response.status_code == 201
    res_data = response.json()
    assert res_data["payment_id"] == "pay_live_test_999"
    assert res_data["failure_category"] == "INSUFFICIENT_FUNDS"
