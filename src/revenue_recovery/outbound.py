"""Outbound communication channels: Retell AI, Vomyra AI, Vapi AI, & WhatsApp Notifications.

Integrates Retell AI Voice API (outbound phone call requesting repayment), Vomyra AI,
Vapi AI Voice API, and Twilio/Meta WhatsApp API (outbound WhatsApp message).
"""

import logging
from typing import Any
import requests

from revenue_recovery.observability import mask_identifier

LOGGER = logging.getLogger(__name__)


class RetellVoiceCallProvider:
    """Outbound AI Voice Call provider via Retell AI API (https://api.retellai.com/v2/create-phone-call).

    Sits behind the deterministic decision engine. Triggered only when notification
    or recovery actions are approved.
    """

    def __init__(
        self,
        api_key: str,
        agent_id: str = "",
        from_number: str = "",
        fallback_phone: str = "",
        timeout_seconds: float = 10.0,
    ):
        self.api_key = api_key.strip()
        self.agent_id = agent_id.strip()
        self.from_number = from_number.strip()
        self.fallback_phone = fallback_phone.strip()
        self.timeout_seconds = timeout_seconds

    def make_call(self, event_id: int, payment_id: str, customer_id: str, message: str, phone: str = "") -> str:
        target_phone = phone.strip() or self.fallback_phone
        if not self.api_key or not self.agent_id:
            LOGGER.info(
                "retell voice call simulated (no API key or Agent ID)",
                extra={"event_id": event_id, "payment_id": mask_identifier(payment_id)},
            )
            return f"retell:simulated:{event_id}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if self.from_number:
            url = "https://api.retellai.com/v2/create-phone-call"
            payload: dict[str, Any] = {
                "from_number": self.from_number,
                "to_number": target_phone or "+1234567890",
                "override_agent_id": self.agent_id,
                "retell_llm_dynamic_variables": {
                    "payment_id": payment_id,
                    "customer_id": customer_id,
                    "event_id": str(event_id),
                    "message": message,
                },
            }
        else:
            url = "https://api.retellai.com/v2/create-web-call"
            payload = {
                "agent_id": self.agent_id,
                "retell_llm_dynamic_variables": {
                    "payment_id": payment_id,
                    "customer_id": customer_id,
                    "event_id": str(event_id),
                    "message": message,
                },
            }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self.timeout_seconds)
            LOGGER.info(
                "retell voice call request completed",
                extra={
                    "event_id": event_id,
                    "payment_id": mask_identifier(payment_id),
                    "status_code": response.status_code,
                },
            )
            if response.status_code in (200, 201):
                data = response.json()
                call_id = data.get("call_id") or data.get("id") or "initiated"
                return f"retell:live:{call_id}"
            return f"retell:failed:{response.status_code}"
        except Exception as exc:
            LOGGER.warning(
                "retell voice call request failed",
                extra={
                    "event_id": event_id,
                    "payment_id": mask_identifier(payment_id),
                    "error_type": type(exc).__name__,
                },
            )
            return f"retell:error:{type(exc).__name__}"


class VomyraVoiceCallProvider:
    """Outbound AI Voice Call provider via Vomyra AI / Bolna AI API (https://api.vomyra.ai/v1/calls)."""

    def __init__(
        self,
        api_key: str,
        agent_id: str = "",
        api_url: str = "https://api.vomyra.ai/v1/calls",
        fallback_phone: str = "",
        timeout_seconds: float = 10.0,
    ):
        self.api_key = api_key.strip()
        self.agent_id = agent_id.strip()
        self.api_url = api_url.strip() or "https://api.vomyra.ai/v1/calls"
        self.fallback_phone = fallback_phone.strip()
        self.timeout_seconds = timeout_seconds

    def make_call(self, event_id: int, payment_id: str, customer_id: str, message: str, phone: str = "") -> str:
        target_phone = phone.strip() or self.fallback_phone
        if not self.api_key or not self.agent_id:
            LOGGER.info(
                "vomyra voice call simulated (no API key or Agent ID)",
                extra={"event_id": event_id, "payment_id": mask_identifier(payment_id)},
            )
            return f"vomyra:simulated:{event_id}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "agent_id": self.agent_id,
            "recipient_phone_number": target_phone or "+1234567890",
            "user_data": {
                "payment_id": payment_id,
                "customer_id": customer_id,
                "event_id": str(event_id),
                "message": message,
            },
        }

        try:
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=self.timeout_seconds)
            LOGGER.info(
                "vomyra voice call request completed",
                extra={
                    "event_id": event_id,
                    "payment_id": mask_identifier(payment_id),
                    "status_code": response.status_code,
                },
            )
            if response.status_code in (200, 201):
                data = response.json()
                call_id = data.get("call_id") or data.get("id") or "initiated"
                return f"vomyra:live:{call_id}"
            return f"vomyra:failed:{response.status_code}"
        except Exception as exc:
            LOGGER.warning(
                "vomyra voice call request failed",
                extra={
                    "event_id": event_id,
                    "payment_id": mask_identifier(payment_id),
                    "error_type": type(exc).__name__,
                },
            )
            return f"vomyra:error:{type(exc).__name__}"


class VapiVoiceCallProvider:
    """Outbound AI Voice Call provider via Vapi AI API (https://api.vapi.ai/call/phone)."""

    def __init__(
        self,
        api_key: str,
        assistant_id: str = "",
        phone_number_id: str = "",
        fallback_phone: str = "",
        timeout_seconds: float = 10.0,
    ):
        self.api_key = api_key.strip()
        self.assistant_id = assistant_id.strip()
        self.phone_number_id = phone_number_id.strip()
        self.fallback_phone = fallback_phone.strip()
        self.timeout_seconds = timeout_seconds

    def make_call(self, event_id: int, payment_id: str, customer_id: str, message: str, phone: str = "") -> str:
        target_phone = phone.strip() or self.fallback_phone
        if not self.api_key:
            LOGGER.info(
                "vapi voice call simulated (no API key)",
                extra={"event_id": event_id, "payment_id": mask_identifier(payment_id)},
            )
            return f"vapi:simulated:{event_id}"

        url = "https://api.vapi.ai/call/phone"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "type": "outboundPhoneCall",
            "customer": {
                "number": target_phone or "+1234567890",
            },
        }
        if self.phone_number_id:
            payload["phoneNumberId"] = self.phone_number_id
        if self.assistant_id:
            payload["assistantId"] = self.assistant_id

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self.timeout_seconds)
            LOGGER.info(
                "vapi voice call request completed",
                extra={
                    "event_id": event_id,
                    "payment_id": mask_identifier(payment_id),
                    "status_code": response.status_code,
                },
            )
            if response.status_code in (200, 201):
                data = response.json()
                call_id = data.get("id", "initiated")
                return f"vapi:live:{call_id}"
            return f"vapi:failed:{response.status_code}"
        except Exception as exc:
            LOGGER.warning(
                "vapi voice call request failed",
                extra={
                    "event_id": event_id,
                    "payment_id": mask_identifier(payment_id),
                    "error_type": type(exc).__name__,
                },
            )
            return f"vapi:error:{type(exc).__name__}"


class TwilioWhatsAppProvider:
    """WhatsApp Notification Provider via Twilio WhatsApp API."""

    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        whatsapp_from: str = "whatsapp:+14155238886",
        timeout_seconds: float = 10.0,
    ):
        self.account_sid = account_sid.strip()
        self.auth_token = auth_token.strip()
        self.whatsapp_from = whatsapp_from.strip()
        self.timeout_seconds = timeout_seconds

    def send_whatsapp(self, event_id: int, payment_id: str, message: str, phone: str = "") -> str:
        if not self.account_sid or not self.auth_token:
            LOGGER.info(
                "whatsapp message simulated (no Twilio credentials)",
                extra={"event_id": event_id, "payment_id": mask_identifier(payment_id)},
            )
            return f"whatsapp:simulated:{event_id}"

        target_phone = phone.strip() or "+1234567890"
        if not target_phone.startswith("whatsapp:"):
            target_phone = f"whatsapp:{target_phone}"

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        data = {
            "From": self.whatsapp_from,
            "To": target_phone,
            "Body": message,
        }
        try:
            response = requests.post(
                url,
                data=data,
                auth=(self.account_sid, self.auth_token),
                timeout=self.timeout_seconds,
            )
            LOGGER.info(
                "twilio whatsapp request completed",
                extra={
                    "event_id": event_id,
                    "payment_id": mask_identifier(payment_id),
                    "status_code": response.status_code,
                },
            )
            if response.status_code in (200, 201):
                res_data = response.json()
                sid = res_data.get("sid", "sent")
                return f"whatsapp:live:{sid}"
            return f"whatsapp:failed:{response.status_code}"
        except Exception as exc:
            LOGGER.warning(
                "twilio whatsapp request failed",
                extra={
                    "event_id": event_id,
                    "payment_id": mask_identifier(payment_id),
                    "error_type": type(exc).__name__,
                },
            )
            return f"whatsapp:error:{type(exc).__name__}"


class MultiChannelNotificationProvider:
    """Orchestrates outbound dispatches across Log Audit, AI Voice Call (Retell/Vomyra/Vapi), and WhatsApp."""

    def __init__(
        self,
        voice_provider: Any = None,
        whatsapp_provider: Any = None,
        vapi_provider: Any = None,
    ):
        self.voice_provider = voice_provider or vapi_provider
        self.whatsapp_provider = whatsapp_provider

    def send(self, context: Any, message: str) -> str:
        dispatches = []
        dispatches.append(f"log:{context.event_id}")

        if self.voice_provider:
            voice_ref = self.voice_provider.make_call(
                event_id=context.event_id,
                payment_id=context.payment_id,
                customer_id=context.customer_id,
                message=message,
                phone=getattr(context, "customer_phone", ""),
            )
            dispatches.append(voice_ref)

        if self.whatsapp_provider:
            wa_ref = self.whatsapp_provider.send_whatsapp(
                event_id=context.event_id,
                payment_id=context.payment_id,
                message=message,
                phone=getattr(context, "customer_phone", ""),
            )
            dispatches.append(wa_ref)

        LOGGER.info(
            "multi-channel notification dispatched",
            extra={
                "event_id": context.event_id,
                "payment_id": mask_identifier(context.payment_id),
                "channels": dispatches,
            },
        )
        return " | ".join(dispatches)
