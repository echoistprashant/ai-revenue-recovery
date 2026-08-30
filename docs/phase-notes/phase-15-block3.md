# Block 3 Phase Notes — Real Razorpay Test-Mode Integration

## Objective
Wire in real Razorpay test-mode credentials (RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET) and verify end-to-end webhook delivery and outbound retry execution while strictly preserving deterministic decision engine guardrails.

---

## Technical Implementation

1. **Configuration & Credentials (config.py):**
   - Added azorpay_key_id and azorpay_key_secret to Settings, populated strictly from environment variables (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET).
   - Added has_razorpay_credentials property returning True iff both credentials are configured.

2. **Outbound Provider (ctions.py):**
   - Implemented RazorpayRetryProvider to call Razorpay's Orders API (POST https://api.razorpay.com/v1/orders) using HTTP Basic Authentication (key_id, key_secret).
   - **Safety Invariant:** Added explicit check enforcing that FailureCategory.FRAUD_RISK_DECLINE NEVER makes an outbound API call, even if invoked directly.
   - Provider handles network failures, non-2xx HTTP responses, and timeout exceptions without crashing the worker or main API service.

3. **Orchestration (service.py):**
   - Updated PaymentRecoveryService.__init__ to select RazorpayRetryProvider automatically when settings.has_razorpay_credentials is True, falling back to SimulatedRetryProvider when absent.

---

## Verification & Safety Invariants

- **Safety Invariant 1 (Fraud Stop):** FRAUD_RISK_DECLINE events return STOP_RECOVERY at the decision engine phase. ActionExecutor re-validates guardrails prior to side-effect execution and withholding retry.
- **Safety Invariant 2 (Freshness & HMAC Signature):** Signed Razorpay webhook payloads are verified against RAZORPAY_WEBHOOK_SECRET with symmetric 300s window checking.
- **Automated Tests:** Added 	ests/test_razorpay_live.py (6 tests passing).

---

## Manual Verification Record

- **Tunnel URL:** https://unlaced-wisdom-arise.ngrok-free.dev/webhooks/razorpay
- **Verification Method:**
  1. Configured ngrok tunnel on port 8000.
  2. Registered webhook URL in Razorpay Dashboard under Test Mode with active event payment.failed.
  3. Tested webhook path using signed payload simulator (scripts/simulate_razorpay_webhook.py --post).
  4. Verified response status 201 Created with processed PaymentEvent returned.
