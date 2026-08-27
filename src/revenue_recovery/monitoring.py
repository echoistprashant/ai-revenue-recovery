import math
from collections import Counter
from dataclasses import dataclass
from time import perf_counter


@dataclass
class ApplicationMetrics:
    request_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0.0

    def record(self, latency_ms: float, error: bool) -> None:
        self.request_count += 1
        self.error_count += int(error)
        self.total_latency_ms += latency_ms

    def snapshot(self) -> dict[str, float | int]:
        return {
            "request_count": self.request_count,
            "error_count": self.error_count,
            "error_rate": round(self.error_count / self.request_count, 4) if self.request_count else 0.0,
            "average_latency_ms": round(self.total_latency_ms / self.request_count, 4) if self.request_count else 0.0,
        }


def population_stability_index(reference: list[str], current: list[str], epsilon: float = 1e-6) -> float:
    if not reference or not current:
        raise ValueError("reference and current populations are required")
    categories = set(reference) | set(current)
    ref_counts, cur_counts = Counter(reference), Counter(current)
    score = 0.0
    for category in categories:
        ref_rate = max(ref_counts[category] / len(reference), epsilon)
        cur_rate = max(cur_counts[category] / len(current), epsilon)
        score += (cur_rate - ref_rate) * math.log(cur_rate / ref_rate)
    return round(score, 4)


def drift_status(psi: float) -> str:
    if psi >= 0.25:
        return "SIGNIFICANT_DRIFT"
    if psi >= 0.10:
        return "MODERATE_DRIFT"
    return "STABLE"
