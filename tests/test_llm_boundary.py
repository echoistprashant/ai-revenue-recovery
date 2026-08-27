import pytest

from revenue_recovery.llm_boundary import AnalystTools, ApprovedCommunication, CommunicationGenerator, RevenueAnalyst
from revenue_recovery.models import FailureCategory, RecoveryAction


def test_communication_uses_approved_action_only() -> None:
    message = CommunicationGenerator().generate(ApprovedCommunication(RecoveryAction.STOP_RECOVERY, FailureCategory.FRAUD_RISK_DECLINE, 100))
    assert "contact support" in message.lower()
    assert "retry" not in message.lower()


def test_analyst_exposes_exactly_read_only_tools() -> None:
    tools = AnalystTools(lambda: {"rate": 0.5}, lambda: {}, lambda: {}, lambda n: [])
    assert tools.names == ("get_recovery_metrics", "get_failure_breakdown", "get_gateway_health", "get_top_priority_cases")
    with pytest.raises(ValueError):
        tools.call("execute_retry")


def test_analyst_is_grounded_in_tool_results() -> None:
    tools = AnalystTools(lambda: {"rate": 0.5}, lambda: {"BANK": 2}, lambda: {"BANK": "healthy"}, lambda n: [{"id": 1}])
    analyst = RevenueAnalyst(tools)
    assert "0.5" in analyst.answer("what is the recovery rate?")
    assert "BANK" in analyst.answer("which failure category is largest?")
    assert "healthy" in analyst.answer("is the bank healthy?")
    assert "1" in analyst.answer("show priority cases")


def test_analyst_reports_tool_failure_without_inventing_value() -> None:
    def broken():
        raise RuntimeError("database unavailable")
    tools = AnalystTools(broken, lambda: {}, lambda: {}, lambda n: [])
    answer = RevenueAnalyst(tools).answer("recovery metrics")
    assert "database unavailable" in answer
    assert "could not answer" in answer.lower()
