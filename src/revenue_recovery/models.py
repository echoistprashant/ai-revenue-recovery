from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FailureCategory(StrEnum):
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    EXPIRED_CARD = "EXPIRED_CARD"
    INVALID_CARD = "INVALID_CARD"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    BANK_DECLINED = "BANK_DECLINED"
    GATEWAY_OR_NETWORK_FAILURE = "GATEWAY_OR_NETWORK_FAILURE"
    FRAUD_RISK_DECLINE = "FRAUD_RISK_DECLINE"
    PAYMENT_METHOD_FAILURE = "PAYMENT_METHOD_FAILURE"
    TEMPORARY_BANK_ISSUE = "TEMPORARY_BANK_ISSUE"


class PaymentMethod(StrEnum):
    CARD = "CARD"
    UPI = "UPI"
    NET_BANKING = "NET_BANKING"
    WALLET = "WALLET"


class BaselineAction(StrEnum):
    RETRY_LATER = "RETRY_LATER"
    STOP_RECOVERY = "STOP_RECOVERY"


class PaymentEventCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    payment_id: str = Field(min_length=1, max_length=100)
    attempt_id: str = Field(min_length=1, max_length=100)
    customer_id: str = Field(min_length=1, max_length=100)
    subscription_id: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    payment_method: PaymentMethod
    gateway: str = Field(min_length=1, max_length=100)
    bank: str = Field(min_length=1, max_length=100)
    failure_code: str = Field(min_length=1, max_length=100)
    timestamp: datetime
    previous_success_count: int = Field(default=0, ge=0)
    previous_failure_count: int = Field(default=0, ge=0)
    customer_age_days: int = Field(default=0, ge=0)
    subscription_value: float = Field(gt=0)
    retry_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def normalize_fields(self) -> "PaymentEventCreate":
        self.currency = self.currency.upper()
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)
        return self


class ProcessedEvent(BaseModel):
    event_id: int
    payment_id: str
    attempt_id: str
    failure_category: FailureCategory
    action: BaselineAction
    retry_delay_hours: int | None
    reason: str
    recovered: bool | None
    recovery_probability: float | None = None
    churn_risk: float | None = None
    revenue_at_risk: float | None = None
    priority_score: float | None = None
    model_version: str | None = None
    duplicate: bool = False


class RecoveryMetrics(BaseModel):
    total_failures: int
    resolved_events: int
    recovered_events: int
    unresolved_events: int
    recovery_rate: float
    recovered_revenue: float
    failure_breakdown: dict[str, int]


class PriorityCase(BaseModel):
    payment_id: str
    attempt_id: str
    failure_category: FailureCategory
    amount: float
    recovery_probability: float
    churn_risk: float
    revenue_at_risk: float
    priority_score: float
    model_version: str
