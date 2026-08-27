from datetime import datetime, timezone
import hmac
import hashlib
from typing import Any

from revenue_recovery.adapters.base import BaseGatewayAdapter
from revenue_recovery.models import PaymentEventCreate, PaymentMethod


RAZORPAY_ERROR_CODE_MAP = {
    "BAD_REQUEST_PAYMENT_ACCOUNT_INSUFFICIENT_BALANCE": "insufficient_funds",
    "INSUFFICIENT_FUNDS": "insufficient_funds",
    "BAD_REQUEST_PAYMENT_CARD_EXPIRED": "card_expired",
    "EXPIRED_CARD": "card_expired",
    "BAD_REQUEST_PAYMENT_CARD_INVALID": "invalid_card",
    "INVALID_CARD": "invalid_card",
    "BAD_REQUEST_PAYMENT_AUTHENTICATION_FAILED": "authentication_failed",
    "AUTHENTICATION_FAILURE": "authentication_failed",
    "GATEWAY_ERROR": "gateway_timeout",
    "GATEWAY_TIMEOUT": "gateway_timeout",
    "FRAUD_RISK_DECLINE": "fraud_suspected",
    "BAD_REQUEST_PAYMENT_DECLINED_BY_BANK": "bank_declined",
    "BANK_DECLINED": "bank_declined",
    "PAYMENT_METHOD_FAILURE": "payment_method_unavailable",
    "TEMPORARY_BANK_ISSUE": "bank_temporarily_unavailable",
}



class RazorpayAdapter(BaseGatewayAdapter):
    """Adapter for Razorpay payment gateway webhooks."""

    def verify_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        if not signature or not secret:
            return False
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected_signature, signature)

    def normalize_event(self, payload: dict[str, Any]) -> PaymentEventCreate:
        event_name = payload.get("event", "payment.failed")
        payload_data = payload.get("payload", {})
        
        # Payment entity can be nested under payment or payment.entity
        payment_obj = payload_data.get("payment", {})
        entity = payment_obj.get("entity", payment_obj)
        notes = entity.get("notes", {})

        payment_id = entity.get("id") or payload.get("id") or f"pay_rzp_{int(datetime.now().timestamp())}"
        attempt_id = str(notes.get("attempt_id", "att_1"))
        customer_id = entity.get("customer_id") or notes.get("customer_id") or "cust_rzp_default"
        subscription_id = entity.get("subscription_id") or notes.get("subscription_id") or "sub_rzp_default"
        
        # Convert amount from paise to rupees if amount > 100 or integer
        raw_amount = float(entity.get("amount", 1000.0))
        amount = raw_amount / 100.0 if raw_amount >= 100 and entity.get("amount_refunded") is None else raw_amount

        currency = entity.get("currency", "INR").upper()

        raw_method = str(entity.get("method", "card")).lower()
        method_map = {
            "card": PaymentMethod.CARD,
            "upi": PaymentMethod.UPI,
            "netbanking": PaymentMethod.NET_BANKING,
            "wallet": PaymentMethod.WALLET,
        }
        payment_method = method_map.get(raw_method, PaymentMethod.CARD)

        gateway = "RAZORPAY"
        bank = entity.get("bank") or (entity.get("card", {}).get("issuer") if isinstance(entity.get("card"), dict) else None) or "HDFC"

        error_code = entity.get("error_code") or entity.get("error_reason") or notes.get("failure_code") or "BAD_REQUEST_PAYMENT_ACCOUNT_INSUFFICIENT_BALANCE"
        failure_code = RAZORPAY_ERROR_CODE_MAP.get(str(error_code).upper(), "insufficient_funds")


        created_at_ts = entity.get("created_at")
        if created_at_ts:
            ts = datetime.fromtimestamp(int(created_at_ts), tz=timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        prev_succ = int(notes.get("previous_success_count", 2))
        prev_fail = int(notes.get("previous_failure_count", 1))
        cust_age = int(notes.get("customer_age_days", 90))
        sub_val = float(notes.get("subscription_value", amount))
        retry_cnt = int(notes.get("retry_count", 0))

        return PaymentEventCreate(
            payment_id=payment_id,
            attempt_id=attempt_id,
            customer_id=customer_id,
            subscription_id=subscription_id,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            gateway=gateway,
            bank=bank,
            failure_code=failure_code,
            timestamp=ts,
            previous_success_count=prev_succ,
            previous_failure_count=prev_fail,
            customer_age_days=cust_age,
            subscription_value=sub_val,
            retry_count=retry_cnt,
        )
