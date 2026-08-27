import argparse
import hashlib
import hmac
import json
import os
import sys
import requests

# Add src to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))


def create_sample_razorpay_webhook(
    event_type: str = "payment.failed",
    payment_id: str = "pay_rzp_sim_1001",
    amount_in_paise: int = 249900,
    method: str = "card",
    error_code: str = "BAD_REQUEST_PAYMENT_ACCOUNT_INSUFFICIENT_BALANCE",
) -> dict:
    return {
        "entity": "event",
        "account_id": "acc_sim_rzp_01",
        "event": event_type,
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "entity": "payment",
                    "amount": amount_in_paise,
                    "currency": "INR",
                    "status": "failed",
                    "method": method,
                    "bank": "HDFC",
                    "error_code": error_code,
                    "error_description": "Payment failed due to insufficient funds.",
                    "notes": {
                        "customer_id": "cust_sim_88",
                        "subscription_id": "sub_sim_99",
                        "attempt_id": "att_1",
                        "previous_success_count": 3,
                        "previous_failure_count": 1,
                        "customer_age_days": 120,
                        "subscription_value": 2499.0,
                        "retry_count": 0,
                    },
                    "created_at": 1772198400,
                }
            }
        },
        "created_at": 1772198400,
    }


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate a signed Razorpay webhook event.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/webhooks/razorpay", help="API webhook URL")
    parser.add_argument("--secret", default=os.getenv("RAZORPAY_WEBHOOK_SECRET", "test_webhook_secret"), help="Webhook secret")
    parser.add_argument("--event", default="payment.failed", help="Razorpay event type")
    parser.add_argument("--error-code", default="BAD_REQUEST_PAYMENT_ACCOUNT_INSUFFICIENT_BALANCE", help="Razorpay error code")
    parser.add_argument("--post", action="store_true", help="Post to live server endpoint")
    args = parser.parse_args()

    payload_dict = create_sample_razorpay_webhook(
        event_type=args.event,
        error_code=args.error_code,
    )
    payload_bytes = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
    signature = compute_signature(payload_bytes, args.secret)

    print("=== SIMULATED RAZORPAY WEBHOOK Payload ===")
    print(json.dumps(payload_dict, indent=2))
    print(f"\nHMAC-SHA256 Signature (X-Razorpay-Signature): {signature}")

    if args.post:
        print(f"\nPosting to {args.url}...")
        headers = {
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature,
        }
        try:
            res = requests.post(args.url, data=payload_bytes, headers=headers, timeout=5)
            print(f"Response Status: {res.status_code}")
            print("Response Body:")
            print(json.dumps(res.json(), indent=2))
        except Exception as exc:
            print(f"Error posting webhook: {exc}")


if __name__ == "__main__":
    main()
