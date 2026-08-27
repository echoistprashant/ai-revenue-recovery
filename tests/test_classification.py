import pytest

from revenue_recovery.classification import classify_failure
from revenue_recovery.models import FailureCategory


@pytest.mark.parametrize(
    ("code", "category"),
    [
        ("insufficient_funds", FailureCategory.INSUFFICIENT_FUNDS),
        ("card_expired", FailureCategory.EXPIRED_CARD),
        ("invalid_card", FailureCategory.INVALID_CARD),
        ("authentication_failed", FailureCategory.AUTHENTICATION_FAILURE),
        ("bank_declined", FailureCategory.BANK_DECLINED),
        ("gateway_timeout", FailureCategory.GATEWAY_OR_NETWORK_FAILURE),
        ("fraud_suspected", FailureCategory.FRAUD_RISK_DECLINE),
        ("payment_method_unavailable", FailureCategory.PAYMENT_METHOD_FAILURE),
        ("bank_temporarily_unavailable", FailureCategory.TEMPORARY_BANK_ISSUE),
    ],
)
def test_classifies_supported_codes(code: str, category: FailureCategory) -> None:
    assert classify_failure(code) is category


def test_rejects_unknown_code() -> None:
    with pytest.raises(ValueError, match="Unsupported failure code"):
        classify_failure("unknown")
