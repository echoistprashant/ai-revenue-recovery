# Phase 8 — Production Engineering

## Objective

Package the complete system reproducibly and add lightweight operational health and drift checks suitable for a portfolio demonstration.

## Implemented

- Docker image for API, scripts, dashboard, and versioned model
- Docker Compose API and Streamlit services
- GitHub Actions test workflow on pushes and pull requests
- Request count, error count, error rate, and latency metrics
- Model-version exposure through operational metrics
- Population Stability Index drift detector
- Stable, moderate, and significant drift statuses
- Typed drift API endpoint
- Full-system production-oriented documentation

## Scope Decisions

The phase deliberately does not add Kafka, Redis, Celery, Kubernetes, MLflow, or Prometheus/Grafana. The existing local SQLite and in-process architecture are sufficient for this project's scale; those technologies remain documented evolution paths rather than decorative dependencies.

## Drift Detection

The detector compares reference and current categorical distributions using PSI:

```text
Σ (current_rate − reference_rate) × ln(current_rate / reference_rate)
```

Thresholds:

- below 0.10: `STABLE`
- 0.10 through 0.2499: `MODERATE_DRIFT`
- 0.25 or higher: `SIGNIFICANT_DRIFT`

The detector is a monitoring signal only. It does not silently alter financial decisions.

## Verification

- full pytest suite passes
- seeded model training and experiment scripts complete
- drift endpoint detects a payment-method distribution shift
- operational metrics record requests and model version
- Docker and CI definitions are present and scoped
- no credentials are required or embedded
