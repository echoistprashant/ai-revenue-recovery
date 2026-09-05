from dataclasses import dataclass
import os
from pathlib import Path

INLINE = "inline"
QUEUED = "queued"
EXECUTION_MODES = (INLINE, QUEUED)

DEFAULT_TENANT = "default"

# A signing key shorter than this is rejected in production. 32 characters is the
# output width of `secrets.token_urlsafe(24)`, which is what the docs tell operators
# to generate.
MIN_SIGNING_KEY_LENGTH = 32

# The webhook secret every checkout of this repository ships with. It is published in
# `.env.example`, so it authenticates nobody: production refuses to boot while it is
# still in place (see `revenue_recovery.security.resolve_webhook_secret`).
DEFAULT_WEBHOOK_SECRET = "test_webhook_secret"

# How far a signed webhook delivery's own timestamp may sit from now before it is
# refused as a replay. Razorpay sends no timestamp header, so the value checked is
# the `created_at` inside the signed body — an attacker cannot edit it without
# invalidating the signature. Five minutes absorbs ordinary clock skew and gateway
# retry latency while keeping a captured delivery useless within the hour.
DEFAULT_WEBHOOK_TOLERANCE_SECONDS = 300


@dataclass(frozen=True)
class Settings:
    """Runtime configuration.

    Values are read from the environment in :meth:`from_env` rather than in field
    defaults, so importing this module does not freeze the process environment and
    tests can build explicit settings objects.
    """

    database_path: Path = Path("data/revenue_recovery.db")
    database_url: str = ""
    retry_delays_hours: tuple[int, ...] = (1, 6, 24)
    synthetic_seed: int = 20260827
    assumed_remaining_months: int = 6
    recovery_model_path: Path = Path("models/recovery_model.joblib")
    razorpay_webhook_secret: str = DEFAULT_WEBHOOK_SECRET
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    gemini_api_key: str = ""
    deterministic_llm_mode: bool = False
    webhook_tolerance_seconds: int = DEFAULT_WEBHOOK_TOLERANCE_SECONDS
    log_format: str = ""
    log_level: str = "INFO"
    environment: str = "development"
    task_execution_mode: str = INLINE
    task_max_attempts: int = 3
    task_retry_backoff_seconds: int = 60
    worker_poll_interval_seconds: float = 5.0
    worker_batch_size: int = 20
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60
    rate_limit_per_minute: int = 120
    login_rate_limit_per_minute: int = 10
    enforce_https: bool = False
    default_tenant: str = DEFAULT_TENANT
    voice_provider: str = "retell"
    retell_api_key: str = ""
    retell_agent_id: str = ""
    retell_from_number: str = ""
    retell_fallback_phone: str = ""
    vomyra_api_key: str = ""
    vomyra_agent_id: str = ""
    vomyra_api_url: str = "https://api.vomyra.ai/v1/calls"
    vomyra_fallback_phone: str = ""
    vapi_api_key: str = ""
    vapi_assistant_id: str = ""
    vapi_phone_number_id: str = ""
    vapi_fallback_phone: str = ""
    whatsapp_provider: str = "log"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""

    def __post_init__(self) -> None:
        if self.task_execution_mode not in EXECUTION_MODES:
            raise ValueError(f"task_execution_mode must be one of {EXECUTION_MODES}")
        if self.access_token_ttl_minutes <= 0:
            raise ValueError("access_token_ttl_minutes must be positive")
        if self.rate_limit_per_minute <= 0 or self.login_rate_limit_per_minute <= 0:
            raise ValueError("rate limits must be positive")
        if self.webhook_tolerance_seconds <= 0:
            raise ValueError("webhook_tolerance_seconds must be positive")

    @property
    def database_target(self) -> str | Path:
        """Explicit URL when configured, otherwise the SQLite file path."""
        return self.database_url or self.database_path

    @property
    def uses_default_webhook_secret(self) -> bool:
        """True while the publicly published example secret is still configured."""
        return self.razorpay_webhook_secret.strip() == DEFAULT_WEBHOOK_SECRET

    @property
    def has_razorpay_credentials(self) -> bool:
        return bool(self.razorpay_key_id.strip() and self.razorpay_key_secret.strip())

    @property
    def has_retell_credentials(self) -> bool:
        return bool(self.retell_api_key.strip() and self.retell_agent_id.strip())

    @property
    def has_vomyra_credentials(self) -> bool:
        return bool(self.vomyra_api_key.strip() and self.vomyra_agent_id.strip())

    @property
    def has_vapi_credentials(self) -> bool:
        return bool(self.vapi_api_key.strip())

    @property
    def has_whatsapp_credentials(self) -> bool:
        return bool(self.twilio_account_sid.strip() and self.twilio_auth_token.strip())

    @property
    def has_gemini_key(self) -> bool:
        return bool(self.gemini_api_key.strip()) and not self.deterministic_llm_mode

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        if env is not None:
            source = dict(env)
        else:
            source = dict(os.environ)
            # Merge local .env file values if present and not overridden by process env
            dotenv_path = Path(".env")
            if not dotenv_path.exists():
                dotenv_path = Path("../.env")
            if dotenv_path.is_file():
                for line in dotenv_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in source:
                            source[k] = v

        environment = source.get("APP_ENVIRONMENT", "development")
        llm_mode = source.get("LLM_MODE", "gemini").strip().lower()
        return cls(
            database_path=Path(source.get("REVENUE_RECOVERY_DATABASE", "data/revenue_recovery.db")),
            database_url=source.get("DATABASE_URL", ""),
            recovery_model_path=Path(source.get("RECOVERY_MODEL_PATH", "models/recovery_model.joblib")),
            razorpay_webhook_secret=source.get("RAZORPAY_WEBHOOK_SECRET", DEFAULT_WEBHOOK_SECRET),
            razorpay_key_id=source.get("RAZORPAY_KEY_ID", ""),
            razorpay_key_secret=source.get("RAZORPAY_KEY_SECRET", ""),
            gemini_api_key=source.get("GEMINI_API_KEY", ""),
            deterministic_llm_mode=llm_mode == "deterministic",
            webhook_tolerance_seconds=int(
                source.get("WEBHOOK_TOLERANCE_SECONDS", str(DEFAULT_WEBHOOK_TOLERANCE_SECONDS))
            ),
            # Empty means "leave logging alone", which is what tests and an
            # interactive shell want. Production defaults to JSON so a log line is
            # machine-readable without an operator remembering to set anything.
            log_format=source.get("LOG_FORMAT", ""),
            log_level=source.get("LOG_LEVEL", "INFO"),
            environment=environment,
            task_execution_mode=source.get("TASK_EXECUTION_MODE", INLINE),
            task_max_attempts=int(source.get("TASK_MAX_ATTEMPTS", "3")),
            task_retry_backoff_seconds=int(source.get("TASK_RETRY_BACKOFF_SECONDS", "60")),
            worker_poll_interval_seconds=float(source.get("WORKER_POLL_INTERVAL_SECONDS", "5.0")),
            worker_batch_size=int(source.get("WORKER_BATCH_SIZE", "20")),
            jwt_secret_key=source.get("JWT_SECRET_KEY", ""),
            jwt_algorithm=source.get("JWT_ALGORITHM", "HS256"),
            access_token_ttl_minutes=int(source.get("ACCESS_TOKEN_TTL_MINUTES", "60")),
            rate_limit_per_minute=int(source.get("RATE_LIMIT_PER_MINUTE", "120")),
            login_rate_limit_per_minute=int(source.get("LOGIN_RATE_LIMIT_PER_MINUTE", "10")),
            # Plain HTTP is refused in production unless an operator opts out
            # explicitly, so a misconfigured proxy fails loudly instead of serving
            # bearer tokens in clear text.
            enforce_https=_flag(source, "ENFORCE_HTTPS", environment.strip().lower() == "production"),
            default_tenant=source.get("DEFAULT_TENANT", DEFAULT_TENANT),
            voice_provider=source.get("VOICE_PROVIDER", "retell"),
            retell_api_key=source.get("RETELL_API_KEY", ""),
            retell_agent_id=source.get("RETELL_AGENT_ID", ""),
            retell_from_number=source.get("RETELL_FROM_NUMBER", ""),
            retell_fallback_phone=source.get("RETELL_FALLBACK_PHONE", ""),
            vomyra_api_key=source.get("VOMYRA_API_KEY", ""),
            vomyra_agent_id=source.get("VOMYRA_AGENT_ID", ""),
            vomyra_api_url=source.get("VOMYRA_API_URL", "https://api.vomyra.ai/v1/calls"),
            vomyra_fallback_phone=source.get("VOMYRA_FALLBACK_PHONE", ""),
            vapi_api_key=source.get("VAPI_API_KEY", ""),
            vapi_assistant_id=source.get("VAPI_ASSISTANT_ID", ""),
            vapi_phone_number_id=source.get("VAPI_PHONE_NUMBER_ID", ""),
            vapi_fallback_phone=source.get("VAPI_FALLBACK_PHONE", ""),
            whatsapp_provider=source.get("WHATSAPP_PROVIDER", "log"),
            twilio_account_sid=source.get("TWILIO_ACCOUNT_SID", ""),
            twilio_auth_token=source.get("TWILIO_AUTH_TOKEN", ""),
            twilio_whatsapp_from=source.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"),
        )


def _flag(source: dict[str, str], name: str, default: bool) -> bool:
    raw = source.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


DEFAULT_SETTINGS = Settings.from_env()
