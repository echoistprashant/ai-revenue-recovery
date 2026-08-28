import datetime
import hashlib
import hmac
import json
import os
import sys


import pandas as pd
import streamlit as st

# Add current directory to path if running directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dashboard.access import allowed, menu_for
from dashboard.api_client import APIClient, APIClientError, AuthenticationRequiredError
from dashboard.components.ui import (
    get_badge_html,
    inject_custom_css,
    render_disclaimer_banner,
    render_header,
    render_pipeline_flow,
    render_safety_callout,
)

st.set_page_config(
    page_title="AI Revenue Recovery — Control Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()

# ==============================================================================
# SESSION, AUTHENTICATION AND ROLE GATING
# ==============================================================================


class SessionAPIClient(APIClient):
    """The dashboard's client, which treats a dead session as a UI event.

    A 401 can come back from any endpoint at any moment — the token expired, an admin
    deactivated the account, the signing key rotated. Handling it once, here, is why
    no individual panel has to check for it: the token is dropped and the script
    restarts on the login form. ``st.rerun`` raises a ``BaseException``, so it unwinds
    cleanly through the panels' ``except APIClientError`` handlers instead of being
    swallowed by them and reported as a backend outage.
    """

    def _request(self, method: str, endpoint: str, **kwargs):
        try:
            return super()._request(method, endpoint, **kwargs)
        except AuthenticationRequiredError as exc:
            st.session_state.pop("token", None)
            st.session_state.pop("identity", None)
            st.session_state["auth_notice"] = f"Your session has ended — please sign in again. ({exc})"
            st.rerun()


def get_client() -> SessionAPIClient:
    """One client per browser session, carrying whatever token that session holds."""
    if "client" not in st.session_state:
        st.session_state["client"] = SessionAPIClient()
    client = st.session_state["client"]
    client.token = st.session_state.get("token")
    return client


def sign_out(notice: str | None = None) -> None:
    """Forget the token locally and restart the script on the login form.

    The access token is stateless and self-expiring, so signing out is a client-side
    act: what makes an account unusable before its token expires is deactivating it,
    which the backend checks on every single request.
    """
    st.session_state.pop("token", None)
    st.session_state.pop("identity", None)
    if notice:
        st.session_state["auth_notice"] = notice
    st.rerun()


def render_login(client: SessionAPIClient) -> None:
    """Ask for credentials. Nothing else on the page renders until this succeeds."""
    notice = st.session_state.pop("auth_notice", None)
    left, middle, right = st.columns([1, 2, 1])
    with middle:
        if notice:
            st.warning(notice)
        st.markdown("#### 🔐 Sign in")
        st.caption(
            "Roles: VIEWER reads dashboards, OPERATOR ingests events and resolves "
            "escalations, ADMIN manages accounts."
        )
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)
        if submitted:
            if not username or not password:
                st.error("Enter both a username and a password.")
                return
            try:
                token = client.login(username, password)
            except APIClientError as exc:
                # Deliberately unspecific: whether the account exists is not
                # something an unauthenticated caller gets to learn from the UI.
                st.error(f"Sign-in failed: {exc}")
                return
            st.session_state["token"] = token["access_token"]
            st.session_state["identity"] = {
                "username": token["username"],
                "role": str(token["role"]),
                "tenant_id": token["tenant_id"],
                "expires_in_seconds": token["expires_in_seconds"],
            }
            st.rerun()


api_client = get_client()

# Navigation Sidebar
st.sidebar.markdown(
    """
    <div style="text-align: center; padding: 0.5rem 0;">
        <h2 style="margin:0; font-size:1.4rem; color:#6366f1;">⚡ AI Revenue Recovery</h2>
        <p style="margin:0; font-size:0.8rem; color:#94a3b8;">Operational Control Center</p>
    </div>
    <hr style="border-color:#334155; margin: 0.8rem 0;"/>
    """,
    unsafe_allow_html=True,
)

# Backend health needs no token, so it is shown to signed-out visitors too: a failed
# sign-in caused by a stopped backend should not look like a bad password.
st.sidebar.markdown("<hr style='border-color:#334155; margin: 1rem 0;'/>", unsafe_allow_html=True)
try:
    health = api_client.get_health()
    st.sidebar.markdown(
        f"**Backend Status**: <span class='badge badge-success'>Connected ({health.get('status', 'ok')})</span>",
        unsafe_allow_html=True,
    )
except Exception:
    st.sidebar.markdown(
        "**Backend Status**: <span class='badge badge-danger'>Disconnected</span>",
        unsafe_allow_html=True,
    )
    st.sidebar.caption("Ensure FastAPI backend is running at http://127.0.0.1:8000")

# --- Login gate. Nothing below this line renders without a session. ---
if not st.session_state.get("token"):
    render_header()
    render_login(api_client)
    st.stop()

identity = st.session_state["identity"]
role = identity["role"]

st.sidebar.markdown(
    f"""
    <hr style='border-color:#334155; margin: 1rem 0;'/>
    <div style="font-size:0.85rem; line-height:1.7;">
        <span style="color:#94a3b8;">Signed in as</span><br/>
        <strong style="color:#f8fafc;">{identity['username']}</strong>
        <span class="badge badge-success">{role}</span><br/>
        <span style="color:#94a3b8;">Tenant:</span> <code>{identity['tenant_id']}</code>
    </div>
    """,
    unsafe_allow_html=True,
)
if st.sidebar.button("Sign out", use_container_width=True):
    sign_out("Signed out.")

# The menu hides what this role cannot use. That is a convenience, not the control:
# every route re-checks the role server-side on every request, and the backend's 403
# is the authoritative answer — see the require(minimum) dependency in api.py.
menu_options = menu_for(role)
selected_module = st.sidebar.radio("Navigate Control Center", menu_options, index=0)

render_header()
render_disclaimer_banner()

# ==============================================================================
# MODULE 1: EXECUTIVE OVERVIEW
# ==============================================================================
if selected_module == "📊 Executive Overview":
    st.subheader("📊 Executive Overview & Revenue Metrics")
    try:
        metrics = api_client.get_metrics()
        op_metrics = api_client.get_operational_metrics()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Failed Payments", f"{metrics['total_failures']:,}")
        col2.metric("Simulated Recovered Events", f"{metrics['recovered_events']:,}", f"{metrics['resolved_events']} resolved")
        col3.metric("Simulated Recovery Rate", f"{metrics['recovery_rate']:.1%}")
        col4.metric("Simulated Recovered Revenue", f"INR {metrics['recovered_revenue']:,.2f}")

        st.markdown("<br/>", unsafe_allow_html=True)

        col_a, col_b = st.columns([3, 2])

        with col_a:
            st.markdown("#### Failure Category Breakdown")
            breakdown = metrics.get("failure_breakdown", {})
            if breakdown:
                df_breakdown = pd.DataFrame(
                    list(breakdown.items()), columns=["Failure Category", "Count"]
                ).sort_values(by="Count", ascending=False)
                st.bar_chart(df_breakdown.set_index("Failure Category"), color="#6366f1")
            else:
                st.info("No failure events processed yet.")

        with col_b:
            st.markdown("#### System Operations & Model Status")
            st.markdown(
                f"""
                <div class="kpi-card">
                    <div class="kpi-title">Deployed Model Version</div>
                    <div class="kpi-value" style="font-size:1.3rem; color:#a855f7;">{op_metrics.get('model_version', 'N/A')}</div>
                    <div class="kpi-sub">Logistic Regression with held-out ROC-AUC 0.7985</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">API Request Latency & Reliability</div>
                    <div style="display:flex; justify-content:space-between; margin-top:0.5rem;">
                        <div>
                            <span style="font-size:0.8rem; color:#94a3b8;">Total Requests</span><br/>
                            <strong style="color:#f8fafc;">{op_metrics.get('request_count', 0)}</strong>
                        </div>
                        <div>
                            <span style="font-size:0.8rem; color:#94a3b8;">Error Rate</span><br/>
                            <strong style="color:#f8fafc;">{op_metrics.get('error_rate', 0.0):.2%}</strong>
                        </div>
                        <div>
                            <span style="font-size:0.8rem; color:#94a3b8;">Avg Latency</span><br/>
                            <strong style="color:#f8fafc;">{op_metrics.get('average_latency_ms', 0.0):.1f} ms</strong>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    except APIClientError as exc:
        st.error(f"Error loading executive metrics: {exc}")

# ==============================================================================
# MODULE 2: PAYMENT OPERATIONS
# ==============================================================================
elif selected_module == "💳 Payment Operations":
    st.subheader("💳 Payment Event Ingestion & Gateway Adapter")
    st.caption("Submit payment events directly or ingest signed Razorpay gateway webhooks to trigger classification, ML scoring, guardrail checks, and deterministic actions.")

    st.markdown("#### 📝 Internal Schema Form")
    st.markdown("##### Quick Fill Scenario Presets")
    preset_col1, preset_col2, preset_col3, preset_col4 = st.columns(4)

    preset = None
    if preset_col1.button("🟢 Inadequate Funds Event"):
        preset = {
            "payment_id": f"pay_{datetime.datetime.now().strftime('%M%S')}",
            "attempt_id": "att_1",
            "customer_id": "cust_101",
            "subscription_id": "sub_501",
            "amount": 2499.0,
            "currency": "INR",
            "payment_method": "CARD",
            "gateway": "RAZORPAY",
            "bank": "HDFC",
            "failure_code": "card_declined_insufficient_funds",
            "previous_success_count": 5,
            "previous_failure_count": 1,
            "customer_age_days": 180,
            "subscription_value": 2499.0,
            "retry_count": 0,
        }
    if preset_col2.button("🔴 Fraud Hard Stop Event"):
        preset = {
            "payment_id": f"pay_fraud_{datetime.datetime.now().strftime('%M%S')}",
            "attempt_id": "att_1",
            "customer_id": "cust_888",
            "subscription_id": "sub_888",
            "amount": 15000.0,
            "currency": "INR",
            "payment_method": "CARD",
            "gateway": "RAZORPAY",
            "bank": "ICICI",
            "failure_code": "fraud_risk_decline",
            "previous_success_count": 0,
            "previous_failure_count": 3,
            "customer_age_days": 10,
            "subscription_value": 15000.0,
            "retry_count": 0,
        }
    if preset_col3.button("⚠️ High Value Event"):
        preset = {
            "payment_id": f"pay_highval_{datetime.datetime.now().strftime('%M%S')}",
            "attempt_id": "att_1",
            "customer_id": "cust_enterprise",
            "subscription_id": "sub_enterprise",
            "amount": 75000.0,
            "currency": "INR",
            "payment_method": "NET_BANKING",
            "gateway": "RAZORPAY",
            "bank": "SBI",
            "failure_code": "bank_declined_generic",
            "previous_success_count": 12,
            "previous_failure_count": 0,
            "customer_age_days": 365,
            "subscription_value": 75000.0,
            "retry_count": 0,
        }
    if preset_col4.button("🌐 Bank Outage Event"):
        preset = {
            "payment_id": f"pay_outage_{datetime.datetime.now().strftime('%M%S')}",
            "attempt_id": "att_1",
            "customer_id": "cust_outage",
            "subscription_id": "sub_outage",
            "amount": 999.0,
            "currency": "INR",
            "payment_method": "UPI",
            "gateway": "RAZORPAY",
            "bank": "AXIS",
            "failure_code": "temporary_bank_issue",
            "previous_success_count": 2,
            "previous_failure_count": 0,
            "customer_age_days": 60,
            "subscription_value": 999.0,
            "retry_count": 0,
        }

    with st.form("event_ingestion_form"):
        col1, col2, col3 = st.columns(3)
        p_id = col1.text_input("Payment ID", value=preset["payment_id"] if preset else "pay_test_001")
        att_id = col2.text_input("Attempt ID", value=preset["attempt_id"] if preset else "att_1")
        cust_id = col3.text_input("Customer ID", value=preset["customer_id"] if preset else "cust_123")

        col4, col5, col6 = st.columns(3)
        sub_id = col4.text_input("Subscription ID", value=preset["subscription_id"] if preset else "sub_456")
        amount = col5.number_input("Amount (INR)", value=float(preset["amount"]) if preset else 1999.0, min_value=1.0)
        p_method = col6.selectbox("Payment Method", ["CARD", "UPI", "NET_BANKING", "WALLET"], index=0)

        col7, col8, col9 = st.columns(3)
        gateway = col7.text_input("Gateway", value=preset["gateway"] if preset else "RAZORPAY")
        bank = col8.text_input("Bank", value=preset["bank"] if preset else "HDFC")
        f_code = col9.text_input("Failure Code", value=preset["failure_code"] if preset else "card_declined_insufficient_funds")

        col10, col11, col12 = st.columns(3)
        prev_succ = col10.number_input("Previous Successes", value=int(preset["previous_success_count"]) if preset else 4, min_value=0)
        prev_fail = col11.number_input("Previous Failures", value=int(preset["previous_failure_count"]) if preset else 1, min_value=0)
        cust_age = col12.number_input("Customer Age (Days)", value=int(preset["customer_age_days"]) if preset else 120, min_value=0)

        col13, col14 = st.columns(2)
        sub_val = col13.number_input("Subscription Value (INR)", value=float(preset["subscription_value"]) if preset else 1999.0, min_value=1.0)
        retry_cnt = col14.number_input("Current Retry Count", value=int(preset["retry_count"]) if preset else 0, min_value=0)

        submitted = st.form_submit_button("Submit Event to Engine", use_container_width=True)

    if submitted:
        event_payload = {
            "payment_id": p_id,
            "attempt_id": att_id,
            "customer_id": cust_id,
            "subscription_id": sub_id,
            "amount": amount,
            "currency": "INR",
            "payment_method": p_method,
            "gateway": gateway,
            "bank": bank,
            "failure_code": f_code,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "previous_success_count": prev_succ,
            "previous_failure_count": prev_fail,
            "customer_age_days": cust_age,
            "subscription_value": sub_val,
            "retry_count": retry_cnt,
        }

        try:
            with st.spinner("Processing event through decision engine..."):
                result = api_client.ingest_event(event_payload)

            st.success("Event Processed Successfully!")

            res_col1, res_col2 = st.columns(2)

            with res_col1:
                st.markdown("##### 📥 Ingestion & Decision Outcome")
                st.json({
                    "event_id": result.get("event_id"),
                    "payment_id": result.get("payment_id"),
                    "failure_category": result.get("failure_category"),
                    "selected_action": result.get("action"),
                    "retry_delay_hours": result.get("retry_delay_hours"),
                    "reason": result.get("reason"),
                    "duplicate": result.get("duplicate", False),
                })

            with res_col2:
                st.markdown("##### 🧠 ML Model & Risk Scores")
                prob = result.get("recovery_probability")
                churn = result.get("churn_risk")
                rar = result.get("revenue_at_risk")
                p_score = result.get("priority_score")

                # A finished case (fraud decline, capped retry) is never scored, so
                # these are genuinely absent rather than zero, and are shown as such.
                st.markdown(f"""
                - **Recovery Probability**: `{f'{prob:.4f}' if prob is not None else 'not scored'}`
                - **Churn Risk Score**: `{f'{churn:.4f}' if churn is not None else 'not scored'}`
                - **Revenue at Risk**: `{f'INR {rar:,.2f}' if rar is not None else 'not scored'}`
                - **Priority Score**: `{f'{p_score:,.2f}' if p_score is not None else 'not scored'}`
                - **Simulated Final Outcome**: `{result.get('recovered')}`
                """)

        except APIClientError as exc:
            st.error(f"Failed to process event: {exc}")

    with st.expander("🔗 Razorpay Webhook Gateway Adapter — signed gateway callback"):
        st.markdown("#### 🔗 Signed Razorpay Webhook Ingestion & HMAC Verification")
        st.caption("Construct and sign a Razorpay gateway webhook payload with HMAC-SHA256 and transmit it to POST /webhooks/razorpay.")

        w_col1, w_col2, w_col3 = st.columns(3)
        w_event = w_col1.selectbox("Razorpay Event", ["payment.failed", "subscription.halted", "payment.authorized"])
        w_err_code = w_col2.selectbox(
            "Razorpay Error Code",
            [
                "BAD_REQUEST_PAYMENT_ACCOUNT_INSUFFICIENT_BALANCE",
                "BAD_REQUEST_PAYMENT_CARD_EXPIRED",
                "BAD_REQUEST_PAYMENT_CARD_INVALID",
                "BAD_REQUEST_PAYMENT_AUTHENTICATION_FAILED",
                "GATEWAY_ERROR",
                "FRAUD_RISK_DECLINE",
                "BAD_REQUEST_PAYMENT_DECLINED_BY_BANK",
            ],
        )
        w_amount_paise = w_col3.number_input("Amount (Paise)", value=249900, min_value=100)

        w_col4, w_col5 = st.columns(2)
        w_pid = w_col4.text_input("Payment ID", value=f"pay_rzp_live_{datetime.datetime.now().strftime('%M%S')}")
        # Read from the environment, never shipped in the source: this value must match
        # the backend's configured secret, and a real one does not belong in a UI default.
        w_secret = w_col5.text_input(
            "Webhook Secret", value=os.getenv("RAZORPAY_WEBHOOK_SECRET", ""), type="password",
        )
        if not w_secret:
            st.caption(
                "Set `RAZORPAY_WEBHOOK_SECRET` to the backend's configured secret, or paste "
                "it here. Without the matching secret the backend rejects the signature with 401."
            )

        sample_webhook = {
            "entity": "event",
            "account_id": "acc_sim_rzp_01",
            "event": w_event,
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": w_pid,
                        "entity": "payment",
                        "amount": w_amount_paise,
                        "currency": "INR",
                        "status": "failed",
                        "method": "card",
                        "bank": "HDFC",
                        "error_code": w_err_code,
                        "notes": {
                            "customer_id": "cust_rzp_web_1",
                            "subscription_id": "sub_rzp_web_1",
                            "attempt_id": "att_1",
                            "previous_success_count": 4,
                            "previous_failure_count": 1,
                            "customer_age_days": 150,
                            "subscription_value": w_amount_paise / 100.0,
                            "retry_count": 0,
                        },
                        "created_at": int(datetime.datetime.now().timestamp()),
                    }
                }
            },
            "created_at": int(datetime.datetime.now().timestamp()),
        }

        payload_bytes = json.dumps(sample_webhook, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(w_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

        st.markdown("##### 🔑 HMAC-SHA256 Cryptographic Signature (`X-Razorpay-Signature`)")
        st.code(signature, language="text")

        st.markdown("##### 📦 Raw Webhook JSON Payload")
        st.json(sample_webhook)

        if st.button("Transmit Signed Webhook to /webhooks/razorpay", use_container_width=True):
            try:
                with st.spinner("Verifying signature & normalizing payload..."):
                    wh_res = api_client.send_razorpay_webhook(payload_bytes, signature)

                st.success("✅ Signature Verified & Webhook Ingested Successfully!")
                st.markdown(f"**Normalized Failure Category**: `{wh_res.get('failure_category')}`")
                st.markdown(f"**Selected Recovery Action**: `{wh_res.get('action')}`")
                st.markdown(f"**Decision Reason**: {wh_res.get('reason')}")

            except APIClientError as exc:
                st.error(f"Webhook Ingestion Failed: {exc}")


# ==============================================================================
# MODULE 3: PRIORITY CASES
# ==============================================================================
elif selected_module == "🎯 Priority Cases":
    st.subheader("🎯 Priority Cases & Risk Scoring Drill-down")
    st.caption("Priority Score = Recovery Probability × Churn Risk × Revenue at Risk")

    col_ctrl1, col_ctrl2 = st.columns([1, 3])
    limit = col_ctrl1.slider("Limit Cases", min_value=5, max_value=50, value=10)

    try:
        cases = api_client.get_priority_cases(limit=limit)

        if cases:
            df_cases = pd.DataFrame(cases)
            st.dataframe(
                df_cases[
                    [
                        "payment_id",
                        "attempt_id",
                        "failure_category",
                        "amount",
                        "recovery_probability",
                        "churn_risk",
                        "revenue_at_risk",
                        "priority_score",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("#### Case Drill-down Inspection")
            selected_pid = st.selectbox("Select Payment ID to inspect signals", df_cases["payment_id"].tolist())

            case_detail = df_cases[df_cases["payment_id"] == selected_pid].iloc[0]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Recovery Probability", f"{case_detail['recovery_probability']:.2%}")
            c2.metric("Churn Risk", f"{case_detail['churn_risk']:.2f}")
            c3.metric("Revenue at Risk", f"INR {case_detail['revenue_at_risk']:,.2f}")
            c4.metric("Priority Score", f"{case_detail['priority_score']:,.2f}")

        else:
            st.info("No priority cases available yet. Ingest payment events first.")

    except APIClientError as exc:
        st.error(f"Error fetching priority cases: {exc}")

# ==============================================================================
# MODULE 3B: HUMAN REVIEW QUEUE
# ==============================================================================
elif selected_module == "🧑‍⚖️ Human Review Queue":
    st.subheader("🧑‍⚖️ Human Review Queue")
    st.caption(
        "Cases the guardrails escalated instead of acting on — high-value transactions "
        "above the review threshold. Ordered by priority score, so the most valuable "
        "recoverable case is first."
    )

    st.markdown(
        """
        <div style="background-color: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 8px; padding: 0.8rem; margin-bottom: 1rem;">
            <strong>🔒 A reviewer's approval is an input, not an authority.</strong><br/>
            Choosing <code>MANUAL_RETRY</code> re-submits the case to the deterministic
            decision engine, which can still withhold it — a fraud decline, a capped
            retry, or a gateway incident is refused no matter who approves it.
        </div>
        """,
        unsafe_allow_html=True,
    )

    queue_limit = st.slider("Cases to load", min_value=5, max_value=50, value=20)

    try:
        queue = api_client.get_review_queue(limit=queue_limit)

        if not queue:
            st.success("Nothing is waiting for a human. The escalation queue is empty.")
        else:
            df_queue = pd.DataFrame(queue)
            st.dataframe(
                df_queue[
                    [
                        "event_id",
                        "payment_id",
                        "customer_id",
                        "amount",
                        "failure_category",
                        "recovery_probability",
                        "priority_score",
                        "reason",
                        "created_at",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )
            st.markdown("#### Case Review")
            case_id = st.selectbox("Select a case", df_queue["event_id"].tolist())
            case = df_queue[df_queue["event_id"] == case_id].iloc[0]

            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Amount", f"INR {case['amount']:,.2f}")
            r2.metric(
                "Recovery Probability",
                "not scored" if pd.isna(case["recovery_probability"]) else f"{case['recovery_probability']:.2%}",
            )
            r3.metric("Churn Risk", "—" if pd.isna(case["churn_risk"]) else f"{case['churn_risk']:.2f}")
            r4.metric("Priority Score", "—" if pd.isna(case["priority_score"]) else f"{case['priority_score']:,.2f}")

            st.markdown(f"**Why it escalated**: {case['reason']}")
            st.markdown(f"**Current state**: `{case['final_state']}` · **Action**: `{case['action']}`")

            with st.expander("📜 Audit trail for this case"):
                try:
                    trail = api_client.get_audit_log(event_id=int(case_id))
                    if trail:
                        for entry in trail:
                            st.markdown(f"**{entry['created_at']}** — `{entry['event_type']}`")
                            st.json(entry["details"], expanded=False)
                    else:
                        st.info("No audit entries recorded for this case.")
                except APIClientError as exc:
                    st.error(f"Failed to load the audit trail: {exc}")

            if not allowed(role, "OPERATOR"):
                st.info("Resolving a case requires the OPERATOR role. You can read the queue.")
            else:
                with st.form("resolve_case_form"):
                    resolution = st.radio(
                        "Resolution",
                        ["MANUAL_RETRY", "MANUAL_RECOVERED", "WRITTEN_OFF"],
                        captions=[
                            "Re-submit to the decision engine, which may still withhold it.",
                            "The customer paid through another channel — record it as recovered.",
                            "Give up on this case and close it.",
                        ],
                    )
                    note = st.text_area("Reviewer note (recorded in the audit log)", max_chars=500)
                    resolve_submitted = st.form_submit_button("Resolve Case", use_container_width=True)

                if resolve_submitted:
                    try:
                        outcome = api_client.resolve_case(int(case_id), resolution, note)
                    except APIClientError as exc:
                        st.error(f"Resolution failed: {exc}")
                    else:
                        if outcome["executed"]:
                            st.success(f"✅ {outcome['detail']}")
                        else:
                            st.warning(f"🛡️ {outcome['detail']}")
                        st.markdown(
                            f"- **Final state**: `{outcome['final_state']}`\n"
                            f"- **Recovered**: `{outcome['recovered']}`\n"
                            f"- **Action executed**: `{outcome['executed']}`\n"
                            f"- **Resolved by**: `{outcome['resolved_by']}` at `{outcome['resolved_at']}`"
                        )
                        st.caption("Reload the queue to see the case leave it.")

    except APIClientError as exc:
        st.error(f"Failed to load the review queue: {exc}")

# ==============================================================================
# MODULE 4: DECISION CENTER
# ==============================================================================
elif selected_module == "🧠 Decision Center":
    st.subheader("🧠 Centralized Deterministic Decision Engine & Safety Guardrails")

    render_safety_callout()

    st.markdown("#### System Architecture Decision Flow")
    render_pipeline_flow(active_step=4)

    st.markdown("#### Interactive Decision & Guardrail Simulator")
    st.caption("Test how input signals trigger guardrails or deterministic action rules.")

    with st.form("decision_simulator_form"):
        col1, col2, col3 = st.columns(3)
        cat = col1.selectbox(
            "Failure Category",
            [
                "INSUFFICIENT_FUNDS",
                "EXPIRED_CARD",
                "INVALID_CARD",
                "AUTHENTICATION_FAILURE",
                "BANK_DECLINED",
                "GATEWAY_OR_NETWORK_FAILURE",
                "FRAUD_RISK_DECLINE",
                "PAYMENT_METHOD_FAILURE",
                "TEMPORARY_BANK_ISSUE",
            ],
        )
        amount = col2.number_input("Transaction Amount (INR)", value=5000.0, min_value=1.0)
        retries = col3.number_input("Retry Count", value=0, min_value=0)

        col4, col5, col6 = st.columns(3)
        rec_prob = col4.slider("Recovery Probability", min_value=0.0, max_value=1.0, value=0.75)
        inc_active = col5.checkbox("Active Gateway Incident?", value=False)
        rec_method = col6.selectbox("Recommended Method", ["CARD", "UPI", "NET_BANKING", "WALLET", "None"])

        sim_submitted = st.form_submit_button("Evaluate Decision Rules", use_container_width=True)

    if sim_submitted:
        payload = {
            "failure_category": cat,
            "amount": amount,
            "retry_count": retries,
            "recovery_probability": rec_prob,
            "incident_active": inc_active,
            "recommended_method": None if rec_method == "None" else rec_method,
        }

        try:
            decision_res = api_client.get_decision(payload)

            st.markdown("##### 🎯 Decision Output")

            g_rule = decision_res.get("guardrail_rule")
            if g_rule:
                st.warning(f"🛡️ Guardrail Triggered: **{g_rule}**")

            st.markdown(f"""
            - **Selected Action**: `{decision_res.get('action')}`
            - **Guardrail Reason**: {decision_res.get('guardrail_reason')}
            - **Engine Explanation**: {decision_res.get('reason')}
            """)

        except APIClientError as exc:
            st.error(f"Decision evaluation failed: {exc}")

# ==============================================================================
# MODULE 5: RECOVERY OPTIMIZATION
# ==============================================================================
elif selected_module == "🔮 Recovery Optimization":
    st.subheader("🔮 Intelligent Retry Timing & Next-Best Payment Method")
    st.caption("Historical customer payment profiling to recommend optimal retry window and alternative payment method.")

    with st.form("optimization_form"):
        col1, col2 = st.columns(2)
        cust_id = col1.text_input("Customer ID", value="cust_opt_100")
        ref_hour = col2.slider("Reference Hour (UTC)", min_value=0, max_value=23, value=14)

        st.markdown("##### Customer Payment History Sample")
        h1, h2, h3 = st.columns(3)
        hist_method = h1.selectbox("Historical Method", ["UPI", "CARD", "NET_BANKING", "WALLET"])
        hist_succ = h2.checkbox("Historical Success?", value=True)
        hist_hour = h3.slider("Historical Hour", min_value=0, max_value=23, value=20)

        opt_submit = st.form_submit_button("Generate Recommendations", use_container_width=True)

    if opt_submit:
        history_payload = [
            {
                "customer_id": cust_id,
                "timestamp": f"2026-08-20T{hist_hour:02d}:00:00Z",
                "payment_method": hist_method,
                "successful": hist_succ,
            },
            {
                "customer_id": cust_id,
                "timestamp": f"2026-08-21T{hist_hour:02d}:00:00Z",
                "payment_method": hist_method,
                "successful": True,
            },
        ]

        payload = {
            "customer_id": cust_id,
            "reference_hour": ref_hour,
            "history": history_payload,
        }

        try:
            rec = api_client.get_recommendations(payload)

            st.markdown("#### 💡 Optimization Results")

            r1, r2 = st.columns(2)

            with r1:
                st.markdown("##### ⏱️ Recommended Retry Window")
                st.markdown(f"""
                - **Retry After**: `{rec.get('retry_after_hours')} hours`
                - **Preferred Hour**: `{rec.get('preferred_hour')}:00 UTC`
                - **Confidence**: `{rec.get('timing_confidence'):.1%}`
                - **Reason**: {rec.get('timing_reason')}
                """)

            with r2:
                st.markdown("##### 💳 Next-Best Payment Method")
                st.markdown(f"""
                - **Recommended Method**: `{rec.get('recommended_payment_method')}`
                - **Historical Success Rate**: `{rec.get('method_success_rate'):.1%}`
                - **Sample Size**: `{rec.get('method_sample_size')} observations`
                - **Confidence**: `{rec.get('method_confidence'):.1%}`
                - **Reason**: {rec.get('method_reason')}
                """)

        except APIClientError as exc:
            st.error(f"Failed to get recommendations: {exc}")

# ==============================================================================
# MODULE 6: GATEWAY HEALTH
# ==============================================================================
elif selected_module == "🏦 Gateway Health":
    st.subheader("🏦 Bank & Gateway Health Anomaly Detector")
    st.caption("Monitors rolling window failure rates. Triggers systemic incident when failure rate exceeds 3x baseline (min 20 events).")

    with st.form("gateway_health_form"):
        col1, col2 = st.columns(2)
        bank = col1.text_input("Bank Name", value="HDFC")
        gateway = col2.text_input("Gateway Name", value="RAZORPAY")

        col3, col4, col5 = st.columns(3)
        failures = col3.number_input("Observed Failures", value=8, min_value=0)
        total = col4.number_input("Total Events (Min 20)", value=20, min_value=1)
        baseline_rate = col5.number_input("Baseline Failure Rate", value=0.02, min_value=0.001, max_value=1.0)

        gw_submitted = st.form_submit_button("Check Gateway Health", use_container_width=True)

    if gw_submitted:
        payload = {
            "bank": bank,
            "gateway": gateway,
            "failures": failures,
            "total": total,
            "baseline_failure_rate": baseline_rate,
        }

        try:
            gw_res = api_client.get_gateway_health(payload)

            is_inc = gw_res.get("incident_active", False)

            if is_inc:
                st.error(f"🚨 SYSTEMIC INCIDENT DETECTED on {bank} / {gateway}!")
                st.caption("Action Engine will SUPPRESS_RETRY on this gateway to protect customer experience.")
            else:
                st.success(f"✅ Gateway Health Normal for {bank} / {gateway}")

            g1, g2, g3 = st.columns(3)
            g1.metric("Observed Failure Rate", f"{gw_res.get('observed_failure_rate'):.1%}")
            g2.metric("Baseline Failure Rate", f"{gw_res.get('baseline_failure_rate'):.1%}")
            g3.metric("Failure Multiplier", f"{gw_res.get('failure_multiplier'):.1f}x")

        except APIClientError as exc:
            st.error(f"Gateway health check failed: {exc}")

# ==============================================================================
# MODULE 7: CUSTOMER COMMUNICATION
# ==============================================================================
elif selected_module == "💬 Customer Communication":
    st.subheader("💬 Bounded GenAI Customer Communication")

    st.markdown(
        """
        <div style="background-color: rgba(99, 102, 241, 0.1); border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 8px; padding: 0.8rem; margin-bottom: 1rem;">
            <strong>🔒 LLM Bounded Boundary Pattern:</strong><br/>
            <code>Deterministic Engine Approved Action ➔ LLM Message Generator ➔ Customer Text</code><br/>
            The LLM cannot choose financial actions; it only formats customer-facing text for an <em>already-approved</em> action.
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("comm_form"):
        col1, col2, col3 = st.columns(3)
        approved_action = col1.selectbox(
            "Approved Financial Action",
            [
                "RETRY_NOW",
                "RETRY_LATER",
                "CHANGE_PAYMENT_METHOD",
                "SEND_NOTIFICATION",
                "SUPPRESS_RETRY",
                "ESCALATE_TO_HUMAN",
                "STOP_RECOVERY",
            ],
        )
        cat = col2.selectbox("Failure Category", ["INSUFFICIENT_FUNDS", "EXPIRED_CARD", "FRAUD_RISK_DECLINE", "AUTHENTICATION_FAILURE"])
        amount = col3.number_input("Amount (INR)", value=1499.0)

        comm_submitted = st.form_submit_button("Generate Customer Message", use_container_width=True)

    if comm_submitted:
        payload = {
            "action": approved_action,
            "failure_category": cat,
            "amount": amount,
        }

        try:
            comm_res = api_client.generate_communication(payload)

            st.markdown("#### ✉️ Generated Customer Communication")
            st.info(comm_res.get("message"))
            st.caption(f"Action Verified: {comm_res.get('action')}")

        except APIClientError as exc:
            st.error(f"Communication generation failed: {exc}")

# ==============================================================================
# MODULE 8: AI REVENUE ANALYST
# ==============================================================================
elif selected_module == "🤖 AI Revenue Analyst":
    st.subheader("🤖 Tool-Calling AI Revenue Analyst")
    st.caption("Ask natural-language business questions. The AI Analyst answers strictly using 4 read-only analytics tools.")

    st.markdown(
        """
        <div style="background-color: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 8px; padding: 0.6rem 1rem; margin-bottom: 1rem; font-size: 0.85rem;">
            <strong>Approved Read-Only Tools:</strong> <code>get_recovery_metrics()</code> | <code>get_failure_breakdown()</code> | <code>get_gateway_health()</code> | <code>get_top_priority_cases(n)</code>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### Quick Question Prompts")
    q_col1, q_col2, q_col3, q_col4 = st.columns(4)

    prompt = None
    if q_col1.button("📊 Overall Recovery Rate?"):
        prompt = "what is the recovery rate?"
    if q_col2.button("⚠️ Common Failures?"):
        prompt = "what is the failure breakdown?"
    if q_col3.button("🎯 Top Priority Cases?"):
        prompt = "show top 5 priority cases"
    if q_col4.button("🏦 Gateway Status?"):
        prompt = "what is the gateway health status?"

    question = st.text_input("Ask a business question", value=prompt or "What is our current recovery rate and recovered revenue?")

    if st.button("Ask Analyst", use_container_width=True) or prompt:
        try:
            with st.spinner("Analyst executing read-only tools..."):
                analyst_res = api_client.ask_analyst(question)

            st.markdown("#### 💬 Analyst Grounded Response")
            st.success(analyst_res.get("answer"))

        except APIClientError as exc:
            st.error(f"Analyst query failed: {exc}")

# ==============================================================================
# MODULE 9: EXPERIMENTS & WHAT-IF
# ==============================================================================
elif selected_module == "🧪 Experiments & What-If":
    st.subheader("🧪 A/B Testing & What-If Strategy Projection")
    st.caption("Simulates Strategy A (Control) vs Strategy B (Treatment) on a population and evaluates statistical significance.")

    with st.form("experiment_form"):
        col1, col2, col3 = st.columns(3)
        exp_id = col1.text_input("Experiment ID", value="exp_strategy_retry_v2")
        num_events = col2.slider("Synthetic Event Population", min_value=10, max_value=200, value=40)
        treatment_lift = col3.slider("Treatment Lift Parameter", min_value=0.01, max_value=0.30, value=0.12)

        exp_submitted = st.form_submit_button("Run Experiment & Projection", use_container_width=True)

    if exp_submitted:
        events = [
            {
                "event_id": f"event_{i}",
                "amount": 100.0 + (i * 25 % 500),
                "latent_recovery_score": (i * 37 % 100) / 100.0,
            }
            for i in range(num_events)
        ]

        payload = {
            "experiment_id": exp_id,
            "events": events,
            "treatment_lift": treatment_lift,
        }

        try:
            with st.spinner("Running statistical evaluation..."):
                exp_res = api_client.run_experiment(payload)

            st.markdown("#### 📊 Experiment Results Summary")

            ctrl = exp_res.get("control", {})
            treat = exp_res.get("treatment", {})

            e1, e2, e3, e4 = st.columns(4)
            e1.metric("Control Recovery Rate", f"{ctrl.get('recovery_rate'):.1%}")
            e2.metric("Treatment Recovery Rate", f"{treat.get('recovery_rate'):.1%}")
            e3.metric("Rate Delta", f"{exp_res.get('recovery_rate_delta'):+.1%}")
            e4.metric("Revenue Delta", f"INR {exp_res.get('recovered_revenue_delta'):+,.2f}")

            ci = exp_res.get("confidence_interval_95", (0, 0))
            is_sig = exp_res.get("statistically_distinguishable", False)

            if is_sig:
                st.success(f"✅ Statistically Distinguishable Result! 95% CI: [{ci[0]:.2%}, {ci[1]:.2%}]")
            else:
                st.warning(f"⚠️ Result Not Statistically Distinguishable at 95% Confidence Level. CI: [{ci[0]:.2%}, {ci[1]:.2%}]")

        except APIClientError as exc:
            st.error(f"Experiment execution failed: {exc}")

# ==============================================================================
# MODULE 10: MONITORING & DATA DRIFT
# ==============================================================================
elif selected_module == "📈 Monitoring & Data Drift":
    st.subheader("📈 System Monitoring & Population Stability Index (PSI) Data Drift")

    try:
        op_metrics = api_client.get_operational_metrics()

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total API Requests", f"{op_metrics.get('request_count', 0)}")
        m2.metric("HTTP Errors (5xx)", f"{op_metrics.get('error_count', 0)}")
        m3.metric("Error Rate", f"{op_metrics.get('error_rate', 0.0):.2%}")
        m4.metric("Avg Latency", f"{op_metrics.get('average_latency_ms', 0.0):.1f} ms")

        st.markdown("#### ⚙️ Background Recovery Queue")
        st.caption(
            "Approved actions are executed by the worker process, not by the ingesting request, "
            "so a delayed retry survives a restart. Every task is re-checked against the decision "
            "engine before it runs — a queued row is a record of an approval, not authority to act."
        )
        task_stats = api_client.get_task_stats()
        q1, q2, q3, q4, q5 = st.columns(5)
        q1.metric("Execution Mode", str(task_stats.get("execution_mode", "inline")).upper())
        q2.metric("Pending", f"{task_stats.get('PENDING', 0)}")
        q3.metric("Due Now", f"{task_stats.get('due_now', 0)}")
        q4.metric("Completed", f"{task_stats.get('DONE', 0)}")
        q5.metric("Failed", f"{task_stats.get('FAILED', 0)}")

        if task_stats.get("FAILED", 0):
            st.markdown(
                f"{get_badge_html('ATTENTION: approved actions that never executed', 'danger')}",
                unsafe_allow_html=True,
            )

        # Flushing the queue can execute approved actions, so it needs the operator
        # role. The backend enforces that; hiding the button only avoids offering a
        # viewer a control that would answer 403.
        if allowed(role, "OPERATOR"):
            if st.button("Flush Due Background Work", use_container_width=True):
                report = api_client.run_due_tasks()
                st.success(
                    f"Claimed {report.get('claimed', 0)} · executed {report.get('executed', 0)} · "
                    f"withheld by guardrails {report.get('withheld', 0)} · failed {report.get('failed', 0)} · "
                    f"requeued after a stalled worker {report.get('requeued', 0)}"
                )
        else:
            st.caption("Flushing due background work requires the OPERATOR role.")

        st.markdown("#### 🧪 PSI Data Drift Detection Test")
        st.caption("Detects whether payment method distributions shift between training baseline and live inference.")

        col_ref, col_curr = st.columns(2)
        ref_mix = col_ref.selectbox("Reference Distribution", ["Baseline (70% CARD / 30% UPI)", "Balanced (50% CARD / 50% UPI)"])
        curr_mix = col_curr.selectbox("Current Inference Distribution", ["Shifted (20% CARD / 80% UPI)", "Baseline (70% CARD / 30% UPI)"])

        if st.button("Calculate Population Stability Index (PSI)", use_container_width=True):
            ref_list = ["CARD"] * 70 + ["UPI"] * 30 if "70%" in ref_mix else ["CARD"] * 50 + ["UPI"] * 50
            curr_list = ["CARD"] * 20 + ["UPI"] * 80 if "Shifted" in curr_mix else ["CARD"] * 70 + ["UPI"] * 30

            drift_res = api_client.check_drift({"reference": ref_list, "current": curr_list})

            psi_val = drift_res.get("psi", 0.0)
            status_str = drift_res.get("status", "STABLE")

            d1, d2 = st.columns(2)
            d1.metric("PSI Score", f"{psi_val:.4f}")

            if status_str == "STABLE":
                d2.markdown(f"Status: {get_badge_html('STABLE (PSI < 0.10)', 'success')}", unsafe_allow_html=True)
            elif status_str == "MODERATE_DRIFT":
                d2.markdown(f"Status: {get_badge_html('MODERATE DRIFT (0.10 <= PSI < 0.25)', 'warning')}", unsafe_allow_html=True)
            else:
                d2.markdown(f"Status: {get_badge_html('SIGNIFICANT DRIFT (PSI >= 0.25)', 'danger')}", unsafe_allow_html=True)

            st.caption("Note: Data drift is a monitoring alert signal only. It does not automatically modify financial decisions.")

    except APIClientError as exc:
        st.error(f"Failed to load monitoring metrics: {exc}")

# ==============================================================================
# MODULE 11: AUDIT & DECISION HISTORY
# ==============================================================================
elif selected_module == "📜 Audit & Decision History":
    st.subheader("📜 Decision History & Full Audit Log")
    st.caption("Complete auditable log of processed events, deterministic decision reasons, risk scores, and simulated outcomes.")

    hist_limit = st.slider("Max Events to Display", min_value=10, max_value=200, value=50)

    try:
        history_items = api_client.get_history(limit=hist_limit)

        if history_items:
            df_hist = pd.DataFrame(history_items)

            st.dataframe(
                df_hist[
                    [
                        "event_id",
                        "payment_id",
                        "attempt_id",
                        "customer_id",
                        "amount",
                        "failure_category",
                        "action",
                        "reason",
                        "final_state",
                        "recovered",
                        "priority_score",
                        "event_timestamp",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("#### 🔍 Per-Event Audit Trail")
            st.caption(
                "Every decision and every executed action writes an immutable audit row. "
                "Selecting an event shows that trail: what was classified, what the model "
                "scored, which guardrail fired, and what the worker actually did."
            )
            audit_event_id = st.selectbox("Event ID", df_hist["event_id"].tolist())
            trail = api_client.get_audit_log(event_id=int(audit_event_id))
            if trail:
                for entry in trail:
                    st.markdown(
                        f"**{entry['created_at']}** — `{entry['event_type']}` "
                        f"<span style='color:#94a3b8;'>(audit #{entry['audit_id']})</span>",
                        unsafe_allow_html=True,
                    )
                    st.json(entry["details"], expanded=False)
            else:
                st.info("No audit entries recorded for this event.")

        else:
            st.info("No decision history recorded in database yet.")

    except APIClientError as exc:
        st.error(f"Failed to fetch decision history: {exc}")

# ==============================================================================
# MODULE 12: USER ADMINISTRATION
# ==============================================================================
elif selected_module == "👥 User Administration":
    st.subheader("👥 User Administration")
    st.caption(
        "Accounts in your tenant. Roles are ranked: VIEWER reads, OPERATOR also ingests "
        "events and resolves escalations, ADMIN also manages accounts."
    )
    st.markdown(
        """
        <div style="background-color: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 0.8rem; margin-bottom: 1rem;">
            <strong>🔒 No role overrides the fraud hard stop.</strong> ADMIN manages
            accounts; it does not gain a path to retry a fraud-risk decline or to exceed
            the retry cap. Those refusals sit below every role in the guardrail chain.
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        accounts = api_client.list_users()

        if accounts:
            st.dataframe(
                pd.DataFrame(accounts)[
                    ["user_id", "username", "role", "tenant_id", "is_active", "created_at", "last_login_at"]
                ],
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("#### Create an account")
        with st.form("create_user_form"):
            u_col1, u_col2, u_col3 = st.columns(3)
            new_username = u_col1.text_input("Username", help="At least 3 characters.")
            new_role = u_col2.selectbox("Role", ["VIEWER", "OPERATOR", "ADMIN"])
            new_tenant = u_col3.text_input(
                "Tenant", value=identity["tenant_id"],
                help="Accounts and their data are isolated per tenant.",
            )
            new_password = st.text_input(
                "Password", type="password",
                help="At least 12 characters. Stored only as a bcrypt hash and never echoed back.",
            )
            create_submitted = st.form_submit_button("Create Account", use_container_width=True)

        if create_submitted:
            try:
                created = api_client.create_user({
                    "username": new_username,
                    "password": new_password,
                    "role": new_role,
                    "tenant_id": new_tenant or None,
                })
            except APIClientError as exc:
                st.error(f"Could not create the account: {exc}")
            else:
                st.success(f"Created `{created['username']}` as {created['role']} in tenant `{created['tenant_id']}`.")

        st.markdown("#### Deactivate an account")
        st.caption(
            "Deactivation takes effect on the account's very next request, including one "
            "made with a token issued before it — the backend re-reads the account row on "
            "every call rather than trusting the token's claims."
        )
        active_names = [a["username"] for a in accounts if a["is_active"]]
        if not active_names:
            st.info("No active accounts to deactivate.")
        else:
            target = st.selectbox("Account", active_names)
            if st.button("Deactivate", use_container_width=True):
                try:
                    disabled = api_client.deactivate_user(target)
                except APIClientError as exc:
                    st.error(f"Could not deactivate the account: {exc}")
                else:
                    st.success(f"`{disabled['username']}` is now inactive.")
                    if disabled["username"] == identity["username"]:
                        sign_out("You deactivated your own account.")

    except APIClientError as exc:
        st.error(f"Failed to load accounts: {exc}")

