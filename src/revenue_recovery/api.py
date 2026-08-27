from fastapi import FastAPI, HTTPException, status

from revenue_recovery.config import DEFAULT_SETTINGS
from revenue_recovery.database import Database
from revenue_recovery.models import PaymentEventCreate, PriorityCase, ProcessedEvent, RecoveryMetrics
from revenue_recovery.service import PaymentRecoveryService, UnsupportedFailureCodeError


def create_app(service: PaymentRecoveryService | None = None) -> FastAPI:
    recovery_service = service or PaymentRecoveryService(Database(DEFAULT_SETTINGS.database_path), DEFAULT_SETTINGS)
    app = FastAPI(title="AI Revenue Recovery", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/events", response_model=ProcessedEvent, status_code=status.HTTP_201_CREATED)
    def ingest_event(event: PaymentEventCreate) -> ProcessedEvent:
        try:
            return recovery_service.process_event(event)
        except UnsupportedFailureCodeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/metrics", response_model=RecoveryMetrics)
    def metrics() -> RecoveryMetrics:
        return recovery_service.get_metrics()

    @app.get("/priority-cases", response_model=list[PriorityCase])
    def priority_cases(limit: int = 10) -> list[PriorityCase]:
        try:
            return recovery_service.get_top_priority_cases(limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app


app = create_app()
