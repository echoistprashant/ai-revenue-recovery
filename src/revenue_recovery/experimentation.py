import hashlib
import math
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ExperimentEvent:
    event_id: str
    amount: float
    latent_recovery_score: float


@dataclass(frozen=True)
class VariantMetrics:
    variant: str
    sample_size: int
    recovered_count: int
    recovery_rate: float
    recovered_revenue: float
    unresolved_count: int


@dataclass(frozen=True)
class ExperimentResult:
    experiment_id: str
    control: VariantMetrics
    treatment: VariantMetrics
    recovery_rate_delta: float
    recovered_revenue_delta: float
    confidence_interval_95: tuple[float, float]
    statistically_distinguishable: bool


@dataclass(frozen=True)
class WhatIfProjection:
    strategy: str
    projected_sample_size: int
    projected_recovery_rate: float
    projected_recovered_revenue: float
    projected_unresolved_count: int


def assign_variant(experiment_id: str, event_id: str) -> str:
    digest = hashlib.sha256(f"{experiment_id}:{event_id}".encode("utf-8")).digest()
    return "treatment" if digest[0] % 2 else "control"


def _metrics(variant: str, events: list[ExperimentEvent], probability_lift: float) -> VariantMetrics:
    recovered = [event for event in events if event.latent_recovery_score < min(0.99, 0.5 + probability_lift)]
    return VariantMetrics(
        variant=variant,
        sample_size=len(events),
        recovered_count=len(recovered),
        recovery_rate=round(len(recovered) / len(events), 4) if events else 0.0,
        recovered_revenue=round(sum(event.amount for event in recovered), 2),
        unresolved_count=len(events) - len(recovered),
    )


def run_experiment(experiment_id: str, events: Iterable[ExperimentEvent], treatment_lift: float = 0.12) -> ExperimentResult:
    if treatment_lift < 0 or treatment_lift >= 0.5:
        raise ValueError("treatment_lift must be between 0 and 0.5")
    control_events: list[ExperimentEvent] = []
    treatment_events: list[ExperimentEvent] = []
    for event in events:
        (treatment_events if assign_variant(experiment_id, event.event_id) == "treatment" else control_events).append(event)
    control = _metrics("control", control_events, 0.0)
    treatment = _metrics("treatment", treatment_events, treatment_lift)
    p_pool = (control.recovered_count + treatment.recovered_count) / max(control.sample_size + treatment.sample_size, 1)
    standard_error = math.sqrt(p_pool * (1 - p_pool) * (1 / max(control.sample_size, 1) + 1 / max(treatment.sample_size, 1)))
    delta = treatment.recovery_rate - control.recovery_rate
    interval = (round(delta - 1.96 * standard_error, 4), round(delta + 1.96 * standard_error, 4))
    return ExperimentResult(
        experiment_id=experiment_id,
        control=control,
        treatment=treatment,
        recovery_rate_delta=round(delta, 4),
        recovered_revenue_delta=round(treatment.recovered_revenue - control.recovered_revenue, 2),
        confidence_interval_95=interval,
        statistically_distinguishable=interval[0] > 0 or interval[1] < 0,
    )


def project_what_if(events: Iterable[ExperimentEvent], strategy: str, probability_lift: float) -> WhatIfProjection:
    if not strategy.strip():
        raise ValueError("strategy is required")
    rows = list(events)
    metrics = _metrics(strategy, rows, probability_lift)
    return WhatIfProjection(strategy, metrics.sample_size, metrics.recovery_rate, metrics.recovered_revenue, metrics.unresolved_count)
