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


class RecoveryAction(StrEnum):
    RETRY_NOW = "RETRY_NOW"
    RETRY_LATER = "RETRY_LATER"
    CHANGE_PAYMENT_METHOD = "CHANGE_PAYMENT_METHOD"
    SEND_NOTIFICATION = "SEND_NOTIFICATION"
    SUPPRESS_RETRY = "SUPPRESS_RETRY"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"
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
    action: RecoveryAction
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


class PaymentHistoryInput(BaseModel):
    customer_id: str
    timestamp: datetime
    payment_method: PaymentMethod
    successful: bool


class OptimizationRequest(BaseModel):
    customer_id: str
    reference_hour: int = Field(ge=0, le=23)
    history: list[PaymentHistoryInput]


class OptimizationResponse(BaseModel):
    customer_id: str
    retry_after_hours: int
    preferred_hour: int
    timing_confidence: float
    timing_reason: str
    recommended_payment_method: PaymentMethod
    method_success_rate: float
    method_sample_size: int
    method_confidence: float
    method_reason: str


class DecisionRequest(BaseModel):
    failure_category: FailureCategory
    amount: float = Field(gt=0)
    retry_count: int = Field(ge=0)
    recovery_probability: float = Field(ge=0, le=1)
    incident_active: bool = False
    last_contact_at: datetime | None = None
    recommended_method: PaymentMethod | None = None
    retry_after_hours: int | None = Field(default=None, ge=0, le=168)


class DecisionResponse(BaseModel):
    action: str
    reason: str
    guardrail_rule: str | None
    guardrail_reason: str


class GatewayHealthRequest(BaseModel):
    bank: str
    gateway: str
    failures: int = Field(ge=0)
    total: int = Field(ge=0)
    baseline_failure_rate: float = Field(default=0.02, gt=0, le=1)

    @model_validator(mode="after")
    def validate_counts(self) -> "GatewayHealthRequest":
        if self.failures > self.total:
            raise ValueError("failures cannot exceed total")
        return self


class GatewayHealthResponse(BaseModel):
    bank: str
    gateway: str
    baseline_failure_rate: float
    observed_failure_rate: float
    failure_multiplier: float
    incident_active: bool


class CommunicationRequest(BaseModel):
    action: RecoveryAction
    failure_category: FailureCategory
    amount: float = Field(gt=0)


class CommunicationResponse(BaseModel):
    message: str
    action: RecoveryAction


class AnalystRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class AnalystResponse(BaseModel):
    answer: str


class ExperimentEventInput(BaseModel):
    event_id: str = Field(min_length=1)
    amount: float = Field(gt=0)
    latent_recovery_score: float = Field(ge=0, le=1)


class ExperimentRequest(BaseModel):
    experiment_id: str = Field(min_length=1, max_length=100)
    events: list[ExperimentEventInput] = Field(min_length=2)
    treatment_lift: float = Field(default=0.12, ge=0, lt=0.5)


class VariantMetricsResponse(BaseModel):
    variant: str
    sample_size: int
    recovered_count: int
    recovery_rate: float
    recovered_revenue: float
    unresolved_count: int


class ExperimentResponse(BaseModel):
    experiment_id: str
    control: VariantMetricsResponse
    treatment: VariantMetricsResponse
    recovery_rate_delta: float
    recovered_revenue_delta: float
    confidence_interval_95: tuple[float, float]
    statistically_distinguishable: bool


class DriftRequest(BaseModel):
    reference: list[str] = Field(min_length=1)
    current: list[str] = Field(min_length=1)


class DriftResponse(BaseModel):
    psi: float
    status: str


class EventHistoryItem(BaseModel):
    event_id: int
    payment_id: str
    attempt_id: str
    customer_id: str
    amount: float
    currency: str
    payment_method: str
    gateway: str
    bank: str
    failure_category: FailureCategory
    event_timestamp: str
    action: RecoveryAction
    reason: str
    final_state: str
    recovered: bool | None = None
    recovery_probability: float | None = None
    churn_risk: float | None = None
    revenue_at_risk: float | None = None
    priority_score: float | None = None
    created_at: str
