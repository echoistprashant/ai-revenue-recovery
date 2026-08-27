from revenue_recovery.models import FailureCategory


FAILURE_CODE_MAP: dict[str, FailureCategory] = {
    "insufficient_funds": FailureCategory.INSUFFICIENT_FUNDS,
    "balance_low": FailureCategory.INSUFFICIENT_FUNDS,
    "card_expired": FailureCategory.EXPIRED_CARD,
    "expired_card": FailureCategory.EXPIRED_CARD,
    "invalid_card": FailureCategory.INVALID_CARD,
    "invalid_card_number": FailureCategory.INVALID_CARD,
    "authentication_failed": FailureCategory.AUTHENTICATION_FAILURE,
    "3ds_failed": FailureCategory.AUTHENTICATION_FAILURE,
    "bank_declined": FailureCategory.BANK_DECLINED,
    "issuer_declined": FailureCategory.BANK_DECLINED,
    "gateway_timeout": FailureCategory.GATEWAY_OR_NETWORK_FAILURE,
    "network_error": FailureCategory.GATEWAY_OR_NETWORK_FAILURE,
    "fraud_suspected": FailureCategory.FRAUD_RISK_DECLINE,
    "risk_declined": FailureCategory.FRAUD_RISK_DECLINE,
    "payment_method_unavailable": FailureCategory.PAYMENT_METHOD_FAILURE,
    "upi_handle_invalid": FailureCategory.PAYMENT_METHOD_FAILURE,
    "bank_temporarily_unavailable": FailureCategory.TEMPORARY_BANK_ISSUE,
    "issuer_unavailable": FailureCategory.TEMPORARY_BANK_ISSUE,
}


def classify_failure(failure_code: str) -> FailureCategory:
    normalized = failure_code.strip().lower()
    try:
        return FAILURE_CODE_MAP[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported failure code: {failure_code}") from exc
