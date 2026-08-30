from dataclasses import dataclass
import logging
from typing import Any, Callable

from revenue_recovery.models import FailureCategory, RecoveryAction
from revenue_recovery.observability import safe_error_text

LOGGER = logging.getLogger(__name__)

TEMPLATES = {
    RecoveryAction.RETRY_LATER: "We couldn't complete your payment. We will try again later; no action is needed right now.",
    RecoveryAction.CHANGE_PAYMENT_METHOD: "We couldn't complete your payment. Please update your payment method to keep your subscription active.",
    RecoveryAction.SEND_NOTIFICATION: "We couldn't complete your payment. Please review your payment details when convenient.",
    RecoveryAction.ESCALATE_TO_HUMAN: "We need a specialist to review this payment. Our team will contact you with the next steps.",
    RecoveryAction.SUPPRESS_RETRY: "We are temporarily pausing payment attempts while the payment network issue is investigated.",
    RecoveryAction.STOP_RECOVERY: "We could not recover this payment automatically. Please contact support for assistance.",
    RecoveryAction.RETRY_NOW: "We are attempting your payment again now.",
}


@dataclass(frozen=True)
class ApprovedCommunication:
    action: RecoveryAction
    category: FailureCategory
    amount: float


class CommunicationGenerator:
    """Generate wording only; the approved action is never selected here."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key.strip() if api_key else None

    def generate(self, approved: ApprovedCommunication) -> str:
        fallback = TEMPLATES[approved.action]
        if not self.api_key:
            return fallback

        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            prompt = (
                "You are a customer notification generator for a recurring payment recovery platform.\n"
                f"The system has ALREADY APPROVED the single action: '{approved.action.value}'.\n"
                f"Payment failure reason: '{approved.category.value}'.\n"
                f"Transaction amount: INR {approved.amount:.2f}.\n\n"
                "INSTRUCTIONS:\n"
                "1. Write clear, professional, concise customer-facing notification text.\n"
                f"2. You MUST strictly align with the approved action ('{approved.action.value}').\n"
                "3. You CANNOT change, override, suggest, or imply a different action than the approved action.\n"
                "4. Do NOT include financial promises or change terms.\n"
                "Output ONLY the final customer message text."
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            text = response.text.strip() if response and response.text else ""
            if text and len(text) <= 500:
                return text
            return fallback
        except Exception as exc:
            LOGGER.warning("Gemini communication generation failed, using fallback: %s", safe_error_text(exc, limit=200))
            return fallback


class AnalystTools:
    """Read-only analytics tools exposed to an analyst model."""

    def __init__(
        self,
        metrics: Callable[[], dict[str, Any]],
        breakdown: Callable[[], dict[str, Any]],
        gateway_health: Callable[[], dict[str, Any]],
        priority: Callable[[int], list[dict[str, Any]]],
    ):
        self._tools = {
            "get_recovery_metrics": metrics,
            "get_failure_breakdown": breakdown,
            "get_gateway_health": gateway_health,
            "get_top_priority_cases": priority,
        }

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise ValueError(f"Unknown or non-approved analyst tool: {name}")
        return self._tools[name](**kwargs)


class RevenueAnalyst:
    def __init__(self, tools: AnalystTools, api_key: str | None = None):
        self.tools = tools
        self.api_key = api_key.strip() if api_key else None

    def answer(self, question: str) -> str:
        if self.api_key:
            try:
                return self._answer_with_gemini(question)
            except Exception as exc:
                LOGGER.warning("Gemini analyst call failed, falling back to deterministic routing: %s", safe_error_text(exc, limit=200))

        return self._answer_fallback(question)

    def _answer_fallback(self, question: str) -> str:
        normalized = question.lower()
        try:
            if any(word in normalized for word in ("gateway", "bank", "incident", "outage")):
                result = self.tools.call("get_gateway_health")
                source = "get_gateway_health"
            elif any(word in normalized for word in ("failure", "reason", "breakdown", "category")):
                result = self.tools.call("get_failure_breakdown")
                source = "get_failure_breakdown"
            elif any(word in normalized for word in ("priority", "case", "customer")):
                result = self.tools.call("get_top_priority_cases", n=3)
                source = "get_top_priority_cases"
            else:
                result = self.tools.call("get_recovery_metrics")
                source = "get_recovery_metrics"
        except Exception as exc:
            return (
                "I could not answer from project data because the approved analytics "
                f"tool failed: {safe_error_text(exc, limit=300)}"
            )
        return f"Source: {source}. Project data: {result}. No financial action was executed."

    def _answer_with_gemini(self, question: str) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)

        def get_recovery_metrics() -> dict[str, Any]:
            return self.tools.call("get_recovery_metrics")

        def get_failure_breakdown() -> dict[str, Any]:
            return self.tools.call("get_failure_breakdown")

        def get_gateway_health() -> dict[str, Any]:
            return self.tools.call("get_gateway_health")

        def get_top_priority_cases(n: int = 3) -> list[dict[str, Any]]:
            return self.tools.call("get_top_priority_cases", n=n)

        tool_map = {
            "get_recovery_metrics": get_recovery_metrics,
            "get_failure_breakdown": get_failure_breakdown,
            "get_gateway_health": get_gateway_health,
            "get_top_priority_cases": get_top_priority_cases,
        }

        system_instruction = (
            "You are a strictly bounded AI Revenue Analyst for an AI payment recovery platform.\n"
            "CRITICAL INVARIANTS:\n"
            "1. You can ONLY answer questions using data returned by the provided tools.\n"
            "2. Every single number, percentage, or amount in your answer MUST come from a tool call made in this turn.\n"
            "3. If a number or detail is not present in tool output, say 'I don't know' or 'Data not available' — NEVER invent figures.\n"
            "4. You CANNOT execute financial decisions, trigger retries, or modify system data."
        )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=list(tool_map.values()),
            temperature=0.1,
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=question,
            config=config,
        )

        calls_made = []
        if response.function_calls:
            for call in response.function_calls:
                fn_name = call.name
                fn_args = dict(call.args) if call.args else {}
                if fn_name in tool_map:
                    result = tool_map[fn_name](**fn_args)
                    calls_made.append(fn_name)
                    followup = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=[
                            types.Content(role="user", parts=[types.Part.from_text(question)]),
                            response.candidates[0].content,
                            types.Content(
                                role="user",
                                parts=[
                                    types.Part.from_function_response(
                                        name=fn_name,
                                        response={"result": result},
                                    )
                                ],
                            ),
                        ],
                        config=config,
                    )
                    if followup and followup.text:
                        return f"Source: {', '.join(calls_made)}. {followup.text.strip()} No financial action was executed."

        if response and response.text:
            return response.text.strip()
        
        return self._answer_fallback(question)
