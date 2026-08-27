import json
import hashlib
import hmac
from fastapi.testclient import TestClient

from revenue_recovery.adapters.razorpay import RazorpayAdapter
from revenue_recovery.api import create_app
from revenue_recovery.models import FailureCategory, PaymentMethod


def test_razorpay_signature_verification() -> None:
    adapter = RazorpayAdapter()
    secret = "secret_key_123"
    payload = b'{"event":"payment.failed"}'
    valid_signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    assert adapter.verify_signature(payload, valid_signature, secret) is True
    assert adapter.verify_signature(payload, "invalid_signature", secret) is False
    assert adapter.verify_signature(payload, valid_signature, "wrong_secret") is False
    assert adapter.verify_signature(payload, "", secret) is False


def test_razorpay_payload_normalization() -> None:
    adapter = RazorpayAdapter()
    sample_payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_rzp_999",
                    "amount": 250000,
                    "currency": "INR",
                    "method": "upi",
                    "bank": "ICICI",
                    "error_code": "BAD_REQUEST_PAYMENT_ACCOUNT_INSUFFICIENT_BALANCE",
                    "notes": {
                        "customer_id": "cust_rzp_test",
                        "subscription_id": "sub_rzp_test",
                        "attempt_id": "att_2",
                        "previous_success_count": 5,
                        "previous_failure_count": 0,
                        "customer_age_days": 200,
                        "subscription_value": 2500.0,
                        "retry_count": 1,
                    },
                    "created_at": 1772198400,
                }
            }
        },
    }

    event = adapter.normalize_event(sample_payload)
    assert event.payment_id == "pay_rzp_999"
    assert event.attempt_id == "att_2"
    assert event.customer_id == "cust_rzp_test"
    assert event.amount == 2500.0
    assert event.payment_method == PaymentMethod.UPI
    assert event.bank == "ICICI"
    assert event.failure_code == "insufficient_funds"



def test_razorpay_webhook_api_success(service) -> None:
    client = TestClient(create_app(service))
    secret = "test_webhook_secret"

    payload_dict = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_webhook_test_100",
                    "amount": 199900,
                    "currency": "INR",
                    "method": "card",
                    "bank": "HDFC",
                    "error_code": "BAD_REQUEST_PAYMENT_ACCOUNT_INSUFFICIENT_BALANCE",
                    "notes": {
                        "customer_id": "cust_wh_1",
                        "subscription_id": "sub_wh_1",
                        "attempt_id": "att_1",
                        "previous_success_count": 3,
                        "previous_failure_count": 0,
                        "customer_age_days": 100,
                        "subscription_value": 1999.0,
                        "retry_count": 0,
                    },
                }
            }
        },
    }
    payload_bytes = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhooks/razorpay",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
        },
    )
    assert response.status_code == 201
    res_data = response.json()
    assert res_data["payment_id"] == "pay_webhook_test_100"
    assert res_data["failure_category"] == FailureCategory.INSUFFICIENT_FUNDS
    assert res_data["action"] is not None


def test_razorpay_webhook_api_unauthorized_on_invalid_signature(service) -> None:
    client = TestClient(create_app(service))
    payload_bytes = b'{"event":"payment.failed"}'

    response = client.post(
        "/webhooks/razorpay",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": "invalid_sig_abc",
        },
    )
    assert response.status_code == 401
    assert "Invalid Razorpay webhook signature" in response.json()["detail"]
