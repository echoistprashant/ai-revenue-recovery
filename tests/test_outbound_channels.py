"""Tests for outbound communication channels (Retell AI, Vomyra AI, Vapi AI, & WhatsApp)."""

from unittest.mock import MagicMock, patch

from revenue_recovery.actions import ActionContext, ActionExecutor
from revenue_recovery.models import FailureCategory, RecoveryAction
from revenue_recovery.outbound import (
    MultiChannelNotificationProvider,
    RetellVoiceCallProvider,
    TwilioWhatsAppProvider,
    VapiVoiceCallProvider,
    VomyraVoiceCallProvider,
)
from revenue_recovery.tasks import TaskType


def test_retell_provider_simulation_mode():
    provider = RetellVoiceCallProvider(api_key="", agent_id="")
    ref = provider.make_call(
        event_id=101,
        payment_id="pay_test123",
        customer_id="cust_test456",
        message="Please retry your payment.",
    )
    assert "retell:simulated:101" in ref


@patch("requests.post")
def test_retell_provider_live_call(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"call_id": "retell_call_888"}
    mock_post.return_value = mock_response

    provider = RetellVoiceCallProvider(
        api_key="key_retell_test",
        agent_id="agent_retell_999",
        from_number="+12135551234",
    )
    ref = provider.make_call(
        event_id=102,
        payment_id="pay_retell_123",
        customer_id="cust_retell_456",
        message="Your subscription renewal failed due to insufficient funds.",
        phone="+919876543210",
    )

    assert "retell:live:retell_call_888" in ref
    assert mock_post.called
    kwargs = mock_post.call_args[1]
    assert kwargs["headers"]["Authorization"] == "Bearer key_retell_test"
    assert kwargs["json"]["override_agent_id"] == "agent_retell_999"
    assert kwargs["json"]["to_number"] == "+919876543210"
    assert kwargs["json"]["from_number"] == "+12135551234"


def test_vomyra_provider_simulation_mode():
    provider = VomyraVoiceCallProvider(api_key="", agent_id="")
    ref = provider.make_call(
        event_id=101,
        payment_id="pay_test123",
        customer_id="cust_test456",
        message="Please retry your payment.",
    )
    assert "vomyra:simulated:101" in ref


@patch("requests.post")
def test_vomyra_provider_live_call(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"call_id": "vomyra_call_555"}
    mock_post.return_value = mock_response

    provider = VomyraVoiceCallProvider(
        api_key="vomyra_test_key",
        agent_id="vomyra_agent_777",
    )
    ref = provider.make_call(
        event_id=102,
        payment_id="pay_vomyra_123",
        customer_id="cust_vomyra_456",
        message="Your subscription renewal failed due to insufficient funds.",
        phone="+919876543210",
    )

    assert "vomyra:live:vomyra_call_555" in ref
    assert mock_post.called
    kwargs = mock_post.call_args[1]
    assert kwargs["headers"]["Authorization"] == "Bearer vomyra_test_key"
    assert kwargs["json"]["agent_id"] == "vomyra_agent_777"
    assert kwargs["json"]["recipient_phone_number"] == "+919876543210"


def test_vapi_provider_simulation_mode():
    provider = VapiVoiceCallProvider(api_key="")
    ref = provider.make_call(
        event_id=101,
        payment_id="pay_test123",
        customer_id="cust_test456",
        message="Please retry your payment.",
    )
    assert "vapi:simulated:101" in ref


@patch("requests.post")
def test_vapi_provider_live_call(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"id": "vapi_call_999"}
    mock_post.return_value = mock_response

    provider = VapiVoiceCallProvider(
        api_key="vapi_test_key",
        assistant_id="asst_123",
        phone_number_id="phone_456",
    )
    ref = provider.make_call(
        event_id=102,
        payment_id="pay_test789",
        customer_id="cust_test789",
        message="Your subscription renewal failed due to insufficient funds.",
        phone="+919876543210",
    )

    assert "vapi:live:vapi_call_999" in ref
    assert mock_post.called
    kwargs = mock_post.call_args[1]
    assert kwargs["headers"]["Authorization"] == "Bearer vapi_test_key"
    assert kwargs["json"]["customer"]["number"] == "+919876543210"


def test_twilio_whatsapp_simulation_mode():
    provider = TwilioWhatsAppProvider(account_sid="", auth_token="")
    ref = provider.send_whatsapp(
        event_id=201,
        payment_id="pay_test123",
        message="Your card payment failed.",
    )
    assert "whatsapp:simulated:201" in ref


@patch("requests.post")
def test_twilio_whatsapp_live_message(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"sid": "SM_whatsapp_123"}
    mock_post.return_value = mock_response

    provider = TwilioWhatsAppProvider(
        account_sid="AC_test_account",
        auth_token="auth_token_123",
        whatsapp_from="whatsapp:+14155238886",
    )
    ref = provider.send_whatsapp(
        event_id=202,
        payment_id="pay_test456",
        message="Payment failed. Click here to update your card.",
        phone="+919876543210",
    )

    assert "whatsapp:live:SM_whatsapp_123" in ref
    assert mock_post.called
    kwargs = mock_post.call_args[1]
    assert kwargs["data"]["From"] == "whatsapp:+14155238886"
    assert kwargs["data"]["To"] == "whatsapp:+919876543210"


def test_multi_channel_notification_provider_with_retell():
    retell = RetellVoiceCallProvider(api_key="", agent_id="")
    whatsapp = TwilioWhatsAppProvider(account_sid="", auth_token="")
    multi = MultiChannelNotificationProvider(voice_provider=retell, whatsapp_provider=whatsapp)

    context = ActionContext(
        event_id=301,
        payment_id="pay_multi_123",
        category=FailureCategory.INSUFFICIENT_FUNDS,
        amount=500.0,
        retry_count=1,
        recovery_probability=0.85,
        customer_id="cust_multi_1",
    )

    ref = multi.send(context, "Payment notification message.")
    assert "log:301" in ref
    assert "retell:simulated:301" in ref
    assert "whatsapp:simulated:301" in ref


def test_fraud_decline_never_triggers_retell_or_whatsapp():
    retell_mock = MagicMock()
    whatsapp_mock = MagicMock()
    multi = MultiChannelNotificationProvider(voice_provider=retell_mock, whatsapp_provider=whatsapp_mock)
    executor = ActionExecutor(notification_provider=multi)

    context = ActionContext(
        event_id=401,
        payment_id="pay_fraud_999",
        category=FailureCategory.FRAUD_RISK_DECLINE,
        amount=1500.0,
        retry_count=0,
        recovery_probability=0.1,
    )

    result = executor.execute(TaskType.SEND_NOTIFICATION, context)
    assert not result.executed
    assert result.revalidated_action == RecoveryAction.STOP_RECOVERY
    # Safety invariant: Fraud hard stop ensures zero calls or messages are sent
    assert not retell_mock.make_call.called
    assert not whatsapp_mock.send_whatsapp.called
