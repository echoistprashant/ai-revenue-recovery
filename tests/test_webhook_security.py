"""Webhook replay protection: freshness checking and the idempotency behind it.

Two guards, tested separately because they fail differently. Freshness decides whether
a delivery is recent enough to look at. Idempotency decides what happens when a
delivery this service has already seen arrives again inside the window — which is a
normal Razorpay retry as well as the shape a replay takes.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from revenue_recovery.actions import ActionContext, ActionExecutor
from revenue_recovery.api import create_app
from revenue_recovery.config import DEFAULT_WEBHOOK_TOLERANCE_SECONDS, Settings
from revenue_recovery.database import Database
from revenue_recovery.security import InsecureWebhookSecretError
from revenue_recovery.service import PaymentRecoveryService
from revenue_recovery.webhook_security import check_freshness, delivery_timestamp

MODEL_PATH = Path("models/recovery_model.joblib")
SECRET = "test_webhook_secret"
PRODUCTION_SECRET = "a-real-looking-webhook-secret-value-32ch"


def signed(payload: dict, secret: str = SECRET) -> tuple[bytes, dict[str, str]]:
    """Return the exact bytes to post and the headers Razorpay would send.

    The signature covers the serialised body, so the test has to post those same
    bytes rather than re-serialising the dict.
    """
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return body, {"Content-Type": "application/json", "X-Razorpay-Signature": signature}


def failed_payment(payment_id: str, *, created_at: int | None, attempt_id: str = "att_1") -> dict:
    payload: dict = {
        "entity": "event",
        "event": "payment.failed",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "amount": 199900,
                    "currency": "INR",
                    "method": "card",
                    "bank": "HDFC",
                    "error_code": "BAD_REQUEST_PAYMENT_ACCOUNT_INSUFFICIENT_BALANCE",
                    "notes": {
                        "customer_id": "cust_wh_1",
                        "subscription_id": "sub_wh_1",
                        "attempt_id": attempt_id,
                        "previous_success_count": 6,
                        "previous_failure_count": 0,
                        "customer_age_days": 400,
                        "subscription_value": 1999.0,
                        "retry_count": 0,
                    },
                }
            }
        },
    }
    if created_at is not None:
        payload["created_at"] = created_at
    return payload


def epoch(offset_seconds: float = 0.0) -> int:
    return int((datetime.now(tz=timezone.utc) + timedelta(seconds=offset_seconds)).timestamp())


# --- delivery_timestamp -------------------------------------------------------


def test_delivery_timestamp_prefers_the_events_own_created_at() -> None:
    payload = failed_payment("pay_a", created_at=1772198400)
    payload["payload"]["payment"]["entity"]["created_at"] = 1772100000
    assert delivery_timestamp(payload) == datetime(2026, 2, 27, 13, 20, tzinfo=timezone.utc)


def test_delivery_timestamp_falls_back_to_the_payment_entity() -> None:
    payload = failed_payment("pay_a", created_at=None)
    payload["payload"]["payment"]["entity"]["created_at"] = 1772198400
    assert delivery_timestamp(payload) == datetime(2026, 2, 27, 13, 20, tzinfo=timezone.utc)


def test_delivery_timestamp_is_none_when_absent_or_unusable() -> None:
    assert delivery_timestamp(failed_payment("pay_a", created_at=None)) is None
    assert delivery_timestamp({"created_at": "not-a-number"}) is None
    assert delivery_timestamp({"created_at": None}) is None
    # `True` is an int in Python. Treating it as epoch 1 would date the delivery to
    # 1970 and reject it for the wrong reason.
    assert delivery_timestamp({"created_at": True}) is None
    assert delivery_timestamp("not a payload") is None
    assert delivery_timestamp({}) is None


# --- check_freshness ----------------------------------------------------------


def test_a_recent_delivery_is_accepted() -> None:
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    result = check_freshness(
        now - timedelta(seconds=30), now=now, tolerance_seconds=300, require_timestamp=True
    )
    assert result.accepted is True
    assert result.skew_seconds == 30


def test_a_stale_delivery_is_refused() -> None:
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    result = check_freshness(
        now - timedelta(seconds=3600), now=now, tolerance_seconds=300, require_timestamp=True
    )
    assert result.accepted is False
    assert "stale" in result.reason


def test_a_delivery_from_the_future_is_refused_just_as_firmly() -> None:
    """A sender whose clock runs ahead would otherwise widen the replay window."""
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    result = check_freshness(
        now + timedelta(seconds=3600), now=now, tolerance_seconds=300, require_timestamp=True
    )
    assert result.accepted is False
    assert "ahead" in result.reason


def test_the_window_boundary_is_inclusive() -> None:
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    assert check_freshness(
        now - timedelta(seconds=300), now=now, tolerance_seconds=300, require_timestamp=True
    ).accepted is True
    assert check_freshness(
        now - timedelta(seconds=301), now=now, tolerance_seconds=300, require_timestamp=True
    ).accepted is False


def test_an_undated_delivery_is_refused_only_where_a_timestamp_is_required() -> None:
    now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    assert check_freshness(None, now=now, tolerance_seconds=300, require_timestamp=False).accepted is True
    refused = check_freshness(None, now=now, tolerance_seconds=300, require_timestamp=True)
    assert refused.accepted is False
    assert "no signed timestamp" in refused.reason.lower()


def test_the_default_window_is_five_minutes() -> None:
    assert DEFAULT_WEBHOOK_TOLERANCE_SECONDS == 300
    assert Settings().webhook_tolerance_seconds == 300


def test_a_non_positive_window_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="webhook_tolerance_seconds"):
        Settings(webhook_tolerance_seconds=0)


# --- the route ----------------------------------------------------------------


def test_a_freshly_signed_delivery_is_processed(service) -> None:
    client = TestClient(create_app(service))
    body, headers = signed(failed_payment("pay_fresh_1", created_at=epoch()))
    response = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["payment_id"] == "pay_fresh_1"


def test_a_captured_delivery_replayed_an_hour_later_is_refused(service) -> None:
    """The signature is still valid — that is the point. Freshness is what stops it."""
    client = TestClient(create_app(service))
    body, headers = signed(failed_payment("pay_stale_1", created_at=epoch(-3600)))
    response = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert response.status_code == 401
    assert "replay" in response.json()["detail"].lower()


def test_an_undated_delivery_is_refused_in_production(service, tmp_path) -> None:
    """A real Razorpay delivery always carries `created_at`; a stripped one does not."""
    production = Settings(
        database_path=tmp_path / "prod.db",
        recovery_model_path=MODEL_PATH,
        environment="production",
        razorpay_webhook_secret=PRODUCTION_SECRET,
        # Set explicitly so this test is about the webhook and not about the
        # production HTTPS rule, which would refuse the TestClient's http:// request.
        enforce_https=False,
    )
    client = TestClient(create_app(service, settings=production, signing_key="k" * 40))
    body, headers = signed(failed_payment("pay_undated_1", created_at=None), PRODUCTION_SECRET)
    response = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert response.status_code == 401
    assert "no signed timestamp" in response.json()["detail"].lower()


def test_an_unparseable_body_does_not_echo_itself_back(service) -> None:
    """A webhook response is a poor place to describe how this service reads input."""
    client = TestClient(create_app(service))
    body = b"{not json at all"
    signature = hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    response = client.post(
        "/webhooks/razorpay",
        content=body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail == "Malformed Razorpay webhook payload"
    assert "not json at all" not in detail


# --- idempotency: a replay inside the window still cannot act twice -----------


class CountingRetryProvider:
    """Records every outbound retry attempt so a test can assert there was one."""

    def __init__(self) -> None:
        self.attempts: list[str] = []

    def attempt_retry(self, context: ActionContext) -> bool:
        self.attempts.append(context.payment_id)
        return True


def test_a_replay_inside_the_window_does_not_retry_the_payment_twice(tmp_path) -> None:
    provider = CountingRetryProvider()
    settings = Settings(database_path=tmp_path / "replay.db", recovery_model_path=MODEL_PATH)
    service = PaymentRecoveryService(
        Database(settings.database_path),
        settings,
        action_executor=ActionExecutor(retry_provider=provider),
    )
    client = TestClient(create_app(service))
    body, headers = signed(failed_payment("pay_replay_1", created_at=epoch()))

    first = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert first.status_code == 201, first.text
    assert first.json()["duplicate"] is False

    # Byte-identical delivery, valid signature, inside the freshness window: exactly
    # what a genuine Razorpay retry and a fast replay both look like.
    second = client.post("/webhooks/razorpay", content=body, headers=headers)
    assert second.status_code == 201, second.text
    assert second.json()["duplicate"] is True
    assert second.json()["event_id"] == first.json()["event_id"]

    assert provider.attempts == ["pay_replay_1"], (
        "The replay must not reach the gateway a second time; idempotency on "
        "(tenant_id, payment_id, attempt_id) returns the first stored decision."
    )


def test_a_genuinely_new_attempt_is_not_treated_as_a_replay(tmp_path) -> None:
    """The idempotency key includes attempt_id, so the next attempt is a new event."""
    provider = CountingRetryProvider()
    settings = Settings(database_path=tmp_path / "attempts.db", recovery_model_path=MODEL_PATH)
    service = PaymentRecoveryService(
        Database(settings.database_path),
        settings,
        action_executor=ActionExecutor(retry_provider=provider),
    )
    client = TestClient(create_app(service))
    for attempt in ("att_1", "att_2"):
        body, headers = signed(failed_payment("pay_multi_1", created_at=epoch(), attempt_id=attempt))
        response = client.post("/webhooks/razorpay", content=body, headers=headers)
        assert response.status_code == 201, response.text
        assert response.json()["duplicate"] is False
    assert len(provider.attempts) == 2


# --- the app refuses to boot with the published secret ------------------------


def test_production_app_refuses_to_boot_with_the_default_webhook_secret(service, tmp_path) -> None:
    """A startup failure an operator sees, rather than a 401 found in live traffic."""
    production = Settings(
        database_path=tmp_path / "boot.db",
        recovery_model_path=MODEL_PATH,
        environment="production",
        razorpay_webhook_secret=SECRET,
        enforce_https=False,
    )
    with pytest.raises(InsecureWebhookSecretError, match="published example value"):
        create_app(service, settings=production, signing_key="k" * 40)


def test_production_app_boots_with_a_real_webhook_secret(service, tmp_path) -> None:
    production = Settings(
        database_path=tmp_path / "boot_ok.db",
        recovery_model_path=MODEL_PATH,
        environment="production",
        razorpay_webhook_secret=PRODUCTION_SECRET,
        enforce_https=False,
    )
    assert create_app(service, settings=production, signing_key="k" * 40) is not None
