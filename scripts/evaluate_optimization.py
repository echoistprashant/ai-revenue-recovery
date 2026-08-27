import json

from revenue_recovery.optimization_evaluation import evaluate_optimization


def main() -> None:
    result = evaluate_optimization()
    print(json.dumps(result.__dict__, indent=2))


if __name__ == "__main__":
    main()
