"""FastAPI wiring: authentication, authorization, and the HTTP surface.

Every route except ``/health``, ``/auth/token``, and the signature-verified Razorpay
webhook requires a bearer token. Authorization is a minimum-role check per route, and
the role is re-read from the database on every request rather than trusted from the
token, so deactivating an account takes effect immediately.

A role widens which routes a request may reach. It never widens what the decision
engine will approve: the only route that can cause a payment action is the review
resolution, and it goes through ``ActionExecutor``, which re-runs the engine.
"""

from dataclasses import asdict
import logging
from time import perf_counter
from typing import Annotated, Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from revenue_recovery.adapters import RazorpayAdapter
from revenue_recovery.anomaly import gateway_health
from revenue_recovery.auth import Role, UnknownUserError, User, UserExistsError, UserRepository
from revenue_recovery.clock import utc_now
from revenue_recovery.config import DEFAULT_SETTINGS, Settings
from revenue_recovery.database import Database
from revenue_recovery.decision_engine import DecisionContext, DecisionEngine
from revenue_recovery.llm_boundary import AnalystTools, ApprovedCommunication, CommunicationGenerator, RevenueAnalyst
from revenue_recovery.experimentation import ExperimentEvent, run_experiment
from revenue_recovery.monitoring import ApplicationMetrics, drift_status, population_stability_index
from revenue_recovery.observability import configure_logging, mask_identifier
from revenue_recovery.models import AnalystRequest, AnalystResponse, AuditEntry, CommunicationRequest, CommunicationResponse, DecisionRequest, DecisionResponse, DriftRequest, DriftResponse, EventHistoryItem, ExperimentRequest, ExperimentResponse, GatewayHealthRequest, GatewayHealthResponse, LoginRequest, OptimizationRequest, OptimizationResponse, PaymentEventCreate, PriorityCase, ProcessedEvent, RecoveryMetrics, ResolveCaseRequest, ResolveCaseResponse, ReviewCase, TokenResponse, UserCreate, UserResponse
from revenue_recovery.optimization import PaymentHistory, recommend_payment_method, recommend_retry_window
from revenue_recovery.rate_limit import RateLimiter
from revenue_recovery.security import TokenError, TokenSigner, WeakPasswordError, resolve_webhook_secret
from revenue_recovery.service import CaseNotReviewableError, PaymentRecoveryService, UnsupportedFailureCodeError
from revenue_recovery.webhook_security import check_freshness, delivery_timestamp

BEARER = HTTPBearer(auto_error=False, description="Access token from POST /auth/token")

LOGGER = logging.getLogger(__name__)


def create_app(
    service: PaymentRecoveryService | None = None,
    settings: Settings | None = None,
    signing_key: str | None = None,
) -> FastAPI:
    active_settings = settings or (service.settings if service else DEFAULT_SETTINGS)
    recovery_service = service or PaymentRecoveryService(Database(active_settings.database_target), active_settings)
    app = FastAPI(title="AI Revenue Recovery", version="0.2.0")
    decision_engine = DecisionEngine()
    communication_generator = CommunicationGenerator()
    application_metrics = ApplicationMetrics()
    users = UserRepository(recovery_service.database)
    signer = TokenSigner(active_settings, signing_key)
    # Both secrets that can authorise a write are resolved here, at boot: a bad one is
    # a startup failure an operator sees, not a 401 discovered in production traffic.
    webhook_secret = resolve_webhook_secret(active_settings)
    request_limiter = RateLimiter(active_settings.rate_limit_per_minute)
    login_limiter = RateLimiter(active_settings.login_rate_limit_per_minute)

    app.state.settings = active_settings
    app.state.users = users
    app.state.signer = signer
    app.state.request_limiter = request_limiter
    app.state.login_limiter = login_limiter

    @app.middleware("http")
    async def enforce_https(request: Request, call_next):
        """Refuse plain HTTP when configured to, before anything reads a token.

        A bearer token in a clear-text request is already disclosed by the time a
        handler runs, so this check happens in middleware and returns rather than
        redirecting — a redirect would still have leaked the first request.
        """
        if active_settings.enforce_https and not _is_secure(request):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "HTTPS is required. Set ENFORCE_HTTPS=false only for local development."},
            )
        return await call_next(request)

    @app.middleware("http")
    async def limit_and_observe(request: Request, call_next):
        decision = request_limiter.check(_client_key(request))
        if not decision.allowed:
            application_metrics.record(0.0, False)
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )
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

    def current_user(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(BEARER)],
    ) -> User:
        """Resolve the caller, or refuse the request.

        The token supplies only a username. Role, tenant, and active status come from
        the ``users`` row, so a revoked or demoted account cannot keep using a token
        that was valid when it was issued.
        """
        if credentials is None or not credentials.credentials:
            raise _unauthorized("Missing bearer token")
        try:
            claims = signer.verify(credentials.credentials)
        except TokenError as exc:
            raise _unauthorized(str(exc)) from exc
        try:
            user = users.get(claims.username)
        except UnknownUserError as exc:
            raise _unauthorized("Account no longer exists") from exc
        if not user.is_active:
            raise _unauthorized("Account is deactivated")
        return user

    def require(minimum: Role) -> Callable[..., User]:
        """Build a dependency that admits ``minimum`` and every stronger role."""

        def dependency(user: Annotated[User, Depends(current_user)]) -> User:
            if not user.can(minimum):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"This action requires the {minimum.value} role or higher",
                )
            return user

        return dependency

    Viewer = Annotated[User, Depends(require(Role.VIEWER))]
    Operator = Annotated[User, Depends(require(Role.OPERATOR))]
    Admin = Annotated[User, Depends(require(Role.ADMIN))]

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/auth/token", response_model=TokenResponse)
    def login(request: Request, payload: LoginRequest) -> TokenResponse:
        """Exchange credentials for an access token.

        Wrong username and wrong password produce the same 401 with the same message,
        so the endpoint does not confirm which usernames exist. Login attempts have
        their own tighter rate limit, keyed by client address.
        """
        decision = login_limiter.check(_client_key(request))
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Try again shortly.",
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )
        user = users.authenticate(payload.username, payload.password)
        if user is None:
            raise _unauthorized("Incorrect username or password")
        token, expires_in = signer.issue(user.username, user.role.value, user.tenant_id)
        return TokenResponse(
            access_token=token, expires_in_seconds=expires_in, role=user.role,
            tenant_id=user.tenant_id, username=user.username,
        )

    @app.get("/auth/me", response_model=UserResponse)
    def whoami(user: Viewer) -> UserResponse:
        return _user_response(user)

    @app.get("/auth/users", response_model=list[UserResponse])
    def list_users(admin: Admin) -> list[UserResponse]:
        """Accounts in the administrator's own tenant."""
        return [_user_response(item) for item in users.list_users(admin.tenant_id)]

    @app.post("/auth/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
    def create_user(payload: UserCreate, admin: Admin) -> UserResponse:
        """Create an account. An administrator can only create users in their own
        tenant, so holding one tenant's admin credentials does not grant access to
        another tenant's data."""
        try:
            created = users.create(
                payload.username, payload.password, Role(payload.role.value), admin.tenant_id,
            )
        except UserExistsError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except (WeakPasswordError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _user_response(created)

    @app.post("/auth/users/{username}/deactivate", response_model=UserResponse)
    def deactivate_user(username: str, admin: Admin) -> UserResponse:
        try:
            target = users.get(username)
        except UnknownUserError as exc:
            raise HTTPException(status_code=404, detail=f"No user named {username!r}") from exc
        if target.tenant_id != admin.tenant_id:
            raise HTTPException(status_code=404, detail=f"No user named {username!r}")
        if target.username == admin.username:
            raise HTTPException(status_code=422, detail="An administrator cannot deactivate their own account")
        return _user_response(users.set_active(username, False))

    @app.post("/events", response_model=ProcessedEvent, status_code=status.HTTP_201_CREATED)
    def ingest_event(event: PaymentEventCreate, operator: Operator) -> ProcessedEvent:
        try:
            return recovery_service.process_event(event, tenant_id=operator.tenant_id)
        except UnsupportedFailureCodeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/webhooks/razorpay", response_model=ProcessedEvent, status_code=status.HTTP_201_CREATED)
    async def razorpay_webhook(
        request: Request,
        x_razorpay_signature: str | None = Header(default=None),
    ) -> ProcessedEvent:
        """Gateway callback, authenticated by HMAC signature rather than by a token.

        Events arrive in the configured default tenant: a Razorpay webhook carries no
        tenant of its own, and guessing one from payload contents would be a way to
        write into another tenant's data.
        """
        body = await request.body()
        adapter = RazorpayAdapter()
        if not x_razorpay_signature or not adapter.verify_signature(body, x_razorpay_signature, webhook_secret):
            LOGGER.warning(
                "razorpay webhook rejected: signature",
                extra={"reason": "invalid_signature", "signature_present": bool(x_razorpay_signature), "body_bytes": len(body)},
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Razorpay webhook signature")
        try:
            payload = await request.json()
        except Exception as exc:
            # The parser's message can quote the body back, so it is logged and not
            # returned: a webhook response is one of the few places a caller learns
            # anything about how this service reads its input.
            LOGGER.warning("razorpay webhook rejected: unparseable body", extra={"reason": "invalid_json", "body_bytes": len(body)}, exc_info=exc)
            raise HTTPException(status_code=400, detail="Malformed Razorpay webhook payload") from exc

        # Freshness is checked only after the signature, because the timestamp is only
        # worth trusting when it is inside bytes that were signed.
        freshness = check_freshness(
            delivery_timestamp(payload),
            now=utc_now(),
            tolerance_seconds=active_settings.webhook_tolerance_seconds,
            require_timestamp=active_settings.is_production,
        )
        if not freshness.accepted:
            LOGGER.warning(
                "razorpay webhook rejected: freshness",
                extra={"reason": "stale_or_undated", "detail": freshness.reason, "skew_seconds": freshness.skew_seconds},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Razorpay webhook delivery refused as a possible replay. {freshness.reason}",
            )

        try:
            event = adapter.normalize_event(payload)
            processed = recovery_service.process_event(event, tenant_id=active_settings.default_tenant)
        except UnsupportedFailureCodeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            LOGGER.warning("razorpay webhook rejected: unusable payload", extra={"reason": "normalization_failed"}, exc_info=exc)
            raise HTTPException(status_code=400, detail="Malformed Razorpay webhook payload") from exc
        LOGGER.info(
            "razorpay webhook accepted",
            extra={
                # Both are Razorpay identifiers and both are join keys back to a real
                # customer's payment history in the gateway dashboard, so both are masked.
                # `event_id` is this service's own row id and is left readable: it is what
                # an operator needs to pull the full record out of the audit trail.
                "payment_id": mask_identifier(processed.payment_id),
                "attempt_id": mask_identifier(processed.attempt_id),
                "event_id": processed.event_id,
                "failure_category": processed.failure_category.value,
                "action": processed.action.value,
                "duplicate": processed.duplicate,
                "skew_seconds": freshness.skew_seconds,
            },
        )
        return processed

    @app.get("/metrics", response_model=RecoveryMetrics)
    def metrics(viewer: Viewer) -> RecoveryMetrics:
        return recovery_service.get_metrics(tenant_id=viewer.tenant_id)

    @app.get("/priority-cases", response_model=list[PriorityCase])
    def priority_cases(viewer: Viewer, limit: int = 10) -> list[PriorityCase]:
        try:
            return recovery_service.get_top_priority_cases(limit, tenant_id=viewer.tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/history", response_model=list[EventHistoryItem])
    def history(viewer: Viewer, limit: int = 50) -> list[EventHistoryItem]:
        try:
            return recovery_service.get_history(limit, tenant_id=viewer.tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/audit-log", response_model=list[AuditEntry])
    def audit_log(viewer: Viewer, event_id: int | None = None, limit: int = 100) -> list[AuditEntry]:
        """The decision and execution trail, scoped to the caller's tenant."""
        try:
            return recovery_service.get_audit_trail(event_id, limit, tenant_id=viewer.tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/review-queue", response_model=list[ReviewCase])
    def review_queue(viewer: Viewer, limit: int = 50) -> list[ReviewCase]:
        """Escalated cases awaiting a human. Viewers can read the queue; resolving
        it requires the operator role."""
        try:
            return recovery_service.get_review_queue(limit, tenant_id=viewer.tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/review-queue/{event_id}/resolve", response_model=ResolveCaseResponse)
    def resolve_case(event_id: int, payload: ResolveCaseRequest, operator: Operator) -> ResolveCaseResponse:
        """Close an escalated case.

        This is the only authenticated route that can lead to a payment action, and it
        cannot approve one on its own: the service re-runs the decision engine, which
        still refuses fraud declines, capped retries, and suppressed routes.
        """
        try:
            return recovery_service.resolve_case(
                event_id, payload.resolution, operator.username, payload.note, tenant_id=operator.tenant_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except CaseNotReviewableError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/recommendations", response_model=OptimizationResponse)
    def recommendations(request: OptimizationRequest, viewer: Viewer) -> OptimizationResponse:
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
    def decide(request: DecisionRequest, viewer: Viewer) -> DecisionResponse:
        """Explain what the engine would decide for a hypothetical event.

        This is a read-only explanation endpoint: it writes nothing and executes
        nothing, and it exposes no way to set the human-review flag.
        """
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
    def health_check(request: GatewayHealthRequest, viewer: Viewer) -> GatewayHealthResponse:
        return GatewayHealthResponse(**gateway_health(
            request.bank, request.gateway, request.failures, request.total,
            request.baseline_failure_rate,
        ).__dict__)

    @app.post("/communication", response_model=CommunicationResponse)
    def communication(request: CommunicationRequest, operator: Operator) -> CommunicationResponse:
        approved = ApprovedCommunication(request.action, request.failure_category, request.amount)
        return CommunicationResponse(message=communication_generator.generate(approved), action=request.action)

    @app.post("/analyst", response_model=AnalystResponse)
    def analyst(request: AnalystRequest, viewer: Viewer) -> AnalystResponse:
        """Read-only analytics questions.

        The analyst's tools are bound to the caller's tenant, so it can only quote
        numbers this user is allowed to see.
        """
        tools = AnalystTools(
            metrics=lambda: recovery_service.get_metrics(tenant_id=viewer.tenant_id).model_dump(),
            breakdown=lambda: recovery_service.get_metrics(tenant_id=viewer.tenant_id).failure_breakdown,
            gateway_health=lambda: {"status": "available from gateway-health endpoint"},
            priority=lambda n: [
                case.model_dump()
                for case in recovery_service.get_top_priority_cases(n, tenant_id=viewer.tenant_id)
            ],
        )
        return AnalystResponse(answer=RevenueAnalyst(tools).answer(request.question))

    @app.post("/experiments", response_model=ExperimentResponse)
    def experiment(request: ExperimentRequest, viewer: Viewer) -> ExperimentResponse:
        result = run_experiment(
            request.experiment_id,
            [ExperimentEvent(**event.model_dump()) for event in request.events],
            treatment_lift=request.treatment_lift,
        )
        return ExperimentResponse.model_validate(asdict(result))

    @app.get("/operational-metrics")
    def operational_metrics(viewer: Viewer) -> dict[str, float | int | str]:
        return application_metrics.snapshot() | {
            "model_version": recovery_service.scorer.model_version if recovery_service.scorer else "unavailable"
        }

    @app.post("/drift", response_model=DriftResponse)
    def drift(request: DriftRequest, viewer: Viewer) -> DriftResponse:
        psi = population_stability_index(request.reference, request.current)
        return DriftResponse(psi=psi, status=drift_status(psi))

    @app.get("/tasks/stats")
    def task_stats(viewer: Viewer) -> dict[str, int | str]:
        return recovery_service.get_task_stats()

    @app.post("/tasks/run-due")
    def run_due_tasks(operator: Operator) -> dict[str, int]:
        """Drain due background work.

        The worker process normally does this; the endpoint exists so a single-process
        deployment and the operations UI can flush the queue on demand. It executes
        nothing on its own authority: every task is re-checked by the decision engine.
        """
        return recovery_service.run_due_tasks()

    return app


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        user_id=user.user_id, username=user.username, role=user.role.value,
        tenant_id=user.tenant_id, is_active=user.is_active,
        created_at=user.created_at, last_login_at=user.last_login_at,
    )


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _is_secure(request: Request) -> bool:
    """Treat a request as secure only on real TLS or a proxy that says so.

    ``X-Forwarded-Proto`` is trusted here because the deployment terminates TLS at a
    proxy in front of this process. If the app is ever exposed directly, the header
    must be stripped at the edge.
    """
    if request.url.scheme == "https":
        return True
    forwarded = request.headers.get("x-forwarded-proto", "")
    return forwarded.split(",")[0].strip().lower() == "https"


def _client_key(request: Request) -> str:
    """Rate-limit key: the client address, or the proxy's first forwarded address."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# Logging is configured for the *process*, not per application object. `create_app` is
# called by the test suite and by the simulation scripts; a factory that tears the root
# logger's handlers out from under its caller is a factory that breaks its host — which
# it did, silently swallowing warnings other tests were asserting on. This module object
# is what `uvicorn revenue_recovery.api:app` loads, so this line is the API's process
# entry point and the right place to own root logging.
configure_logging(
    DEFAULT_SETTINGS.log_format or ("json" if DEFAULT_SETTINGS.is_production else ""),
    DEFAULT_SETTINGS.log_level,
)
app = create_app()
