from dataclasses import dataclass


@dataclass(frozen=True)
class GatewayHealth:
    bank: str
    gateway: str
    baseline_failure_rate: float
    observed_failure_rate: float
    failure_multiplier: float
    incident_active: bool


def gateway_health(bank: str, gateway: str, failures: int, total: int, baseline_failure_rate: float = 0.02, multiplier: float = 3.0, minimum_events: int = 20) -> GatewayHealth:
    if total < 0 or failures < 0 or failures > total:
        raise ValueError("invalid failure counts")
    observed = failures / total if total else 0.0
    actual_multiplier = observed / baseline_failure_rate if baseline_failure_rate else float("inf")
    active = total >= minimum_events and observed >= baseline_failure_rate * multiplier
    return GatewayHealth(bank, gateway, baseline_failure_rate, round(observed, 4), round(actual_multiplier, 4), active)
