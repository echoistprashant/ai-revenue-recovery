from pathlib import Path

from revenue_recovery.training import train_and_evaluate


def main() -> None:
    metadata = train_and_evaluate(
        Path("models/recovery_model.joblib"),
        Path("models/recovery_model_metadata.json"),
    )
    print(metadata)


if __name__ == "__main__":
    main()
