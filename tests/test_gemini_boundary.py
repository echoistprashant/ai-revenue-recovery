"""Tests for Gemini LLM integration, fallback paths, and boundary safety constraints."""

from unittest.mock import MagicMock, patch

import pytest

from revenue_recovery.config import Settings
from revenue_recovery.llm_boundary import (
    AnalystTools,
    ApprovedCommunication,
    CommunicationGenerator,
    RevenueAnalyst,
    TEMPLATES,
)
from revenue_recovery.models import FailureCategory, RecoveryAction


def test_communication_generator_fallback_when_no_api_key():
    """CommunicationGenerator uses static template fallback when api_key is None or empty."""
    generator = CommunicationGenerator(api_key="")
    approved = ApprovedCommunication(
        action=RecoveryAction.RETRY_LATER,
        category=FailureCategory.INSUFFICIENT_FUNDS,
        amount=1500.0,
    )
    result = generator.generate(approved)
    assert result == TEMPLATES[RecoveryAction.RETRY_LATER]


def test_communication_generator_fallback_on_api_error():
    """CommunicationGenerator falls back gracefully to template if Gemini API call fails."""
    generator = CommunicationGenerator(api_key="mock_invalid_key")
    approved = ApprovedCommunication(
        action=RecoveryAction.CHANGE_PAYMENT_METHOD,
        category=FailureCategory.EXPIRED_CARD,
        amount=2500.0,
    )
    with patch("google.genai.Client", side_effect=Exception("API connection error")):
        result = generator.generate(approved)
        assert result == TEMPLATES[RecoveryAction.CHANGE_PAYMENT_METHOD]


def test_communication_generator_gemini_success():
    """CommunicationGenerator returns text from Gemini when API call succeeds."""
    generator = CommunicationGenerator(api_key="mock_valid_key")
    approved = ApprovedCommunication(
        action=RecoveryAction.SEND_NOTIFICATION,
        category=FailureCategory.BANK_DECLINED,
        amount=1999.0,
    )

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Please check your bank account or card details for your INR 1999.00 payment."
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        result = generator.generate(approved)
        assert "1999.00" in result or "check" in result
        mock_client.models.generate_content.assert_called_once()


def test_revenue_analyst_fallback_routing():
    """RevenueAnalyst uses keyword tool routing fallback when no api_key is provided."""
    tools = AnalystTools(
        metrics=lambda: {"total_recovered": 50000},
        breakdown=lambda: {"INSUFFICIENT_FUNDS": 10},
        gateway_health=lambda: {"HDFC": "HEALTHY"},
        priority=lambda n: [{"payment_id": "pay_1", "priority_score": 0.95}],
    )
    analyst = RevenueAnalyst(tools, api_key="")
    
    ans_gateway = analyst.answer("Is there a bank outage?")
    assert "get_gateway_health" in ans_gateway
    assert "HDFC" in ans_gateway

    ans_metrics = analyst.answer("What is the total revenue recovered?")
    assert "get_recovery_metrics" in ans_metrics
    assert "50000" in ans_metrics


def test_revenue_analyst_fallback_on_api_failure():
    """RevenueAnalyst falls back to deterministic routing if Gemini API raises error."""
    tools = AnalystTools(
        metrics=lambda: {"total_recovered": 10000},
        breakdown=lambda: {},
        gateway_health=lambda: {},
        priority=lambda n: [],
    )
    analyst = RevenueAnalyst(tools, api_key="mock_key")

    with patch("google.genai.Client", side_effect=Exception("Gemini quota exceeded")):
        ans = analyst.answer("Show me recovery metrics")
        assert "get_recovery_metrics" in ans
        assert "10000" in ans


def test_deterministic_llm_mode_flag():
    """LLM_MODE=deterministic disables Gemini even if GEMINI_API_KEY is set."""
    settings_gemini = Settings(gemini_api_key="key123", deterministic_llm_mode=False)
    assert settings_gemini.has_gemini_key is True

    settings_deterministic = Settings(gemini_api_key="key123", deterministic_llm_mode=True)
    assert settings_deterministic.has_gemini_key is False
