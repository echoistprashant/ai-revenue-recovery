import json
from dataclasses import asdict

from revenue_recovery.experimentation import ExperimentEvent, project_what_if, run_experiment


def main() -> None:
    events = [ExperimentEvent(f"event-{index}", 500 + (index % 5) * 250, ((index * 37) % 100) / 100) for index in range(500)]
    result = run_experiment("retry-window-v1", events, treatment_lift=0.12)
    projection = project_what_if(events, "retry-after-6h", probability_lift=0.12)
    print(json.dumps({"experiment": asdict(result), "what_if": asdict(projection)}, indent=2))


if __name__ == "__main__":
    main()
