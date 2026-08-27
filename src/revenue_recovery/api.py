from fastapi import FastAPI, Header, HTTPException, Request, status
from dataclasses import asdict
from time import perf_counter

from revenue_recovery.adapters import RazorpayAdapter
from revenue_recovery.anomaly import gateway_health
from revenue_recovery.config import DEFAULT_SETTINGS

from revenue_recovery.database import Database
from revenue_recovery.decision_engine import DecisionContext, DecisionEngine
from revenue_recovery.llm_boundary import AnalystTools, ApprovedCommunication, CommunicationGenerator, RevenueAnalyst
from revenue_recovery.experimentation import ExperimentEvent, run_experiment
from revenue_recovery.monitoring import ApplicationMetrics, drift_status, population_stability_index
from revenue_recovery.models import AnalystRequest, AnalystResponse, CommunicationRequest, CommunicationResponse, DecisionRequest, DecisionResponse, DriftRequest, DriftResponse, EventHistoryItem, ExperimentRequest, ExperimentResponse, GatewayHealthRequest, GatewayHealthResponse, OptimizationRequest, OptimizationResponse, PaymentEventCreate, PriorityCase, ProcessedEvent, RecoveryMetrics
from revenue_recovery.optimization import PaymentHistory, recommend_payment_method, recommend_retry_window
from revenue_recovery.service import PaymentRecoveryService, UnsupportedFailureCodeError


def create_app(service: PaymentRecoveryService | None = None) -> FastAPI:
    recovery_service = service or PaymentRecoveryService(Database(DEFAULT_SETTINGS.database_target), DEFAULT_SETTINGS)
    app = FastAPI(title="AI Revenue Recovery", version="0.1.0")
    decision_engine = DecisionEngine()
    communication_generator = CommunicationGenerator()
    application_metrics = ApplicationMetrics()

    @app.middleware("http")
    async def observe_requests(request, call_next):
        started = perf_counter()
        error = False
        try:
            response = await call_next(request)
            error = response.status_code >= 500
            return response
        except Exception:
            error = True
            raise
        finally:
            application_metrics.record((perf_counter() - started) * 1000, error)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/events", response_model=ProcessedEvent, status_code=status.HTTP_201_CREATED)
    def ingest_event(event: PaymentEventCreate) -> ProcessedEvent:
        try:
            return recovery_service.process_event(event)
        except UnsupportedFailureCodeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/webhooks/razorpay", response_model=ProcessedEvent, status_code=status.HTTP_201_CREATED)
    async def razorpay_webhook(
        request: Request,
        x_razorpay_signature: str | None = Header(default=None),
    ) -> ProcessedEvent:
        body = await request.body()
        adapter = RazorpayAdapter()
        secret = recovery_service.settings.razorpay_webhook_secret
        if not x_razorpay_signature or not adapter.verify_signature(body, x_razorpay_signature, secret):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Razorpay webhook signature")
        try:
            payload = await request.json()
            event = adapter.normalize_event(payload)
            return recovery_service.process_event(event)
        except UnsupportedFailureCodeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Malformed Razorpay webhook payload: {exc}") from exc


    @app.get("/metrics", response_model=RecoveryMetrics)
    def metrics() -> RecoveryMetrics:
        return recovery_service.get_metrics()

    @app.get("/priority-cases", response_model=list[PriorityCase])
    def priority_cases(limit: int = 10) -> list[PriorityCase]:
        try:
            return recovery_service.get_top_priority_cases(limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/history", response_model=list[EventHistoryItem])
    def history(limit: int = 50) -> list[EventHistoryItem]:
        try:
            return recovery_service.get_history(limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


    @app.post("/recommendations", response_model=OptimizationResponse)
    def recommendations(request: OptimizationRequest) -> OptimizationResponse:
        history = [PaymentHistory(**item.model_dump()) for item in request.history]
        timing = recommend_retry_window(request.customer_id, history, request.reference_hour)
        method = recommend_payment_method(request.customer_id, history)
        return OptimizationResponse(
            customer_id=request.customer_id,
            retry_after_hours=timing.retry_after_hours,
            preferred_hour=timing.preferred_hour,
            timing_confidence=timing.confidence,
            timing_reason=timing.reason,
            recommended_payment_method=method.payment_method,
            method_success_rate=method.success_rate,
            method_sample_size=method.sample_size,
            method_confidence=method.confidence,
            method_reason=method.reason,
        )

    @app.post("/decisions", response_model=DecisionResponse)
    def decide(request: DecisionRequest) -> DecisionResponse:
        decision = decision_engine.decide(DecisionContext(
            category=request.failure_category,
            amount=request.amount,
            retry_count=request.retry_count,
            recovery_probability=request.recovery_probability,
            incident_active=request.incident_active,
            last_contact_at=request.last_contact_at,
            recommended_method=request.recommended_method.value if request.recommended_method else None,
            retry_after_hours=request.retry_after_hours,
        ))
        return DecisionResponse(
            action=decision.action,
            reason=decision.reason,
            guardrail_rule=decision.guardrail.rule,
            guardrail_reason=decision.guardrail.reason,
        )

    @app.post("/gateway-health", response_model=GatewayHealthResponse)
    def health_check(request: GatewayHealthRequest) -> GatewayHealthResponse:
        return GatewayHealthResponse(**gateway_health(
            request.bank, request.gateway, request.failures, request.total,
            request.baseline_failure_rate,
        ).__dict__)

    @app.post("/communication", response_model=CommunicationResponse)
    def communication(request: CommunicationRequest) -> CommunicationResponse:
        approved = ApprovedCommunication(request.action, request.failure_category, request.amount)
        return CommunicationResponse(message=communication_generator.generate(approved), action=request.action)

    @app.post("/analyst", response_model=AnalystResponse)
    def analyst(request: AnalystRequest) -> AnalystResponse:
        tools = AnalystTools(
            metrics=lambda: recovery_service.get_metrics().model_dump(),
            breakdown=lambda: recovery_service.get_metrics().failure_breakdown,
            gateway_health=lambda: {"status": "available from gateway-health endpoint"},
            priority=lambda n: [case.model_dump() for case in recovery_service.get_top_priority_cases(n)],
        )
        return AnalystResponse(answer=RevenueAnalyst(tools).answer(request.question))

    @app.post("/experiments", response_model=ExperimentResponse)
    def experiment(request: ExperimentRequest) -> ExperimentResponse:
        result = run_experiment(
            request.experiment_id,
            [ExperimentEvent(**event.model_dump()) for event in request.events],
            treatment_lift=request.treatment_lift,
        )
        return ExperimentResponse.model_validate(asdict(result))

    @app.get("/operational-metrics")
    def operational_metrics() -> dict[str, float | int | str]:
        return application_metrics.snapshot() | {
            "model_version": recovery_service.scorer.model_version if recovery_service.scorer else "unavailable"
        }

    @app.post("/drift", response_model=DriftResponse)
    def drift(request: DriftRequest) -> DriftResponse:
        psi = population_stability_index(request.reference, request.current)
        return DriftResponse(psi=psi, status=drift_status(psi))

    @app.get("/tasks/stats")
    def task_stats() -> dict[str, int | str]:
        return recovery_service.get_task_stats()

    @app.post("/tasks/run-due")
    def run_due_tasks() -> dict[str, int]:
        """Drain due background work.

        The worker process normally does this; the endpoint exists so a single-process
        deployment and the operations UI can flush the queue on demand. It executes
        nothing on its own authority: every task is re-checked by the decision engine.
        """
        return recovery_service.run_due_tasks()

    return app


app = create_app()
