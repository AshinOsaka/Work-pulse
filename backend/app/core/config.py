"""Centralised, typed application configuration.

All configuration is sourced from environment variables (optionally a `.env`
file). Nothing secret has a default value — the application refuses to start
without a strong `JWT_SECRET`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_WEAK_SECRETS = {"change-me", "changeme", "secret", "workpulse", "please-change-me"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        # Startup errors must never echo configuration values (they include secrets) into logs.
        hide_input_in_errors=True,
    )

    # --- Application -------------------------------------------------------
    app_name: str = "WorkPulse"
    environment: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api"
    log_level: str = "INFO"
    log_json: bool = False
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = Field(
        default="",
        description="Comma separated list of allowed browser origins.",
    )

    # --- Database ----------------------------------------------------------
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db: str = "workpulse"
    mongodb_server_selection_timeout_ms: int = 5000
    mongodb_connect_retries: int = 5
    # Connection pool per API process. Total connections = processes x max pool (+ the worker): with 4 API processes
    # and the default 50 that is at most ~250, well inside MongoDB's default limit.
    mongodb_max_pool_size: int = Field(default=50, ge=5, le=500)
    mongodb_min_pool_size: int = Field(default=2, ge=0, le=100)
    # Idle connections are closed after this long, so a quiet process gives connections back.
    mongodb_max_idle_time_ms: int = Field(default=300_000, ge=10_000, le=3_600_000)
    # A request waits at most this long for a free pooled connection before failing (503).
    mongodb_wait_queue_timeout_ms: int = Field(default=10_000, ge=500, le=120_000)

    # --- Authentication ----------------------------------------------------
    jwt_secret: SecretStr
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "workpulse"
    jwt_audience: str = "workpulse-api"
    access_token_expire_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_expire_days: int = Field(default=14, ge=1, le=90)
    refresh_reuse_grace_seconds: int = Field(default=10, ge=0, le=120)
    password_reset_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    email_verification_token_expire_hours: int = Field(default=48, ge=1, le=720)
    trial_period_days: int = 14
    invitation_token_expire_days: int = Field(default=7, ge=1, le=30)
    device_enrollment_expire_hours: int = Field(default=72, ge=1, le=720)

    # --- Desktop agent -------------------------------------------------------
    agent_token_expire_minutes: int = Field(default=30, ge=5, le=240)
    agent_heartbeat_interval_seconds: int = Field(default=60, ge=10, le=600)
    agent_sync_interval_seconds: int = Field(default=30, ge=5, le=600)
    agent_idle_threshold_seconds: int = Field(default=300, ge=60, le=3600)
    agent_max_batch_size: int = Field(default=200, ge=10, le=500)
    # A device is considered offline when no heartbeat arrived for this long.
    agent_offline_after_seconds: int = Field(default=180, ge=30, le=3600)

    # --- Screenshots & object storage -----------------------------------------
    # Screenshots are stored as encrypted objects outside MongoDB (which holds metadata only).
    object_storage_dir: str = "./data/objects"
    # Base64 of 32 random bytes. When unset, a key is derived from JWT_SECRET (HKDF, separate label).
    storage_encryption_key: SecretStr | None = None
    screenshot_url_ttl_seconds: int = Field(default=300, ge=30, le=3600)
    screenshot_max_upload_bytes: int = Field(default=4_000_000, ge=100_000, le=9_000_000)
    screenshot_retention_sweep_seconds: int = Field(default=900, ge=10, le=86_400)

    # --- Scaling ---------------------------------------------------------------------
    # Redis shares realtime events, live-viewing signalling, registries and job leases between API processes.
    # Required when running more than one API process; unset means single-process mode (development).
    redis_url: SecretStr | None = None
    # Run notification dispatch, alert scans, retention, report generation and cache warming in this process.
    # Compose turns this off for API processes and runs them in the dedicated `worker` service instead.
    background_jobs: bool = True
    # How often the productivity cache is refreshed for recent days (seconds).
    productivity_warm_seconds: float = Field(default=600, ge=1, le=86_400)

    # --- Abuse protection ------------------------------------------------------
    # Throttles sign-in, registration, password reset, invitation/verification links and agent sign-in.
    # Counters live in MongoDB, so they hold across API processes. Only switch off for automated test suites.
    rate_limits_enabled: bool = True
    # How often open browser WebSockets re-check that their sign-in session is still active.
    session_check_seconds: float = Field(default=15, ge=0.05, le=300)

    # --- AI assistant ----------------------------------------------------------
    # The assistant is off until a key is provided (environment / secret store - never in code or the repo).
    anthropic_api_key: SecretStr | None = None
    assistant_model: str = "claude-opus-5-5"
    assistant_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    assistant_questions_per_hour: int = Field(default=60, ge=1, le=10_000)

    # --- Alerts & notifications ------------------------------------------------
    alert_scan_seconds: int = Field(default=60, ge=5, le=3600)
    # Agent events older than this (uploaded late from the offline queue) don't raise shift alerts.
    alert_event_freshness_seconds: int = Field(default=900, ge=60, le=86_400)

    # --- Reports -----------------------------------------------------------------
    # Generated files are encrypted in object storage and deleted after this many hours.
    report_retention_hours: int = Field(default=168, ge=1, le=24 * 90)
    report_max_days: int = Field(default=366, ge=1, le=731)
    # Rows in a PDF (CSV and Excel always hold every row).
    report_pdf_max_rows: int = Field(default=5000, ge=100, le=50_000)
    # A TrueType font with wide Unicode coverage for PDFs. Empty: common system locations are tried.
    report_pdf_font: str = ""
    # Concurrent reports per requester.
    report_max_active_per_user: int = Field(default=3, ge=1, le=20)

    # --- Live screen viewing (WebRTC; the API only relays signalling) ----------
    live_connect_timeout_seconds: int = Field(default=45, ge=10, le=300)
    live_reconnect_grace_seconds: int = Field(default=30, ge=5, le=300)
    # Comma separated, e.g. "stun:stun.example.com:3478". Empty: host candidates only (same network).
    live_stun_urls: str = ""
    # TURN relays for viewers behind NAT, e.g. "turn:turn.example.com:3478?transport=udp".
    live_turn_urls: str = ""
    # Shared secret of the TURN server (coturn `static-auth-secret`): short-lived credentials are minted per session.
    live_turn_secret: SecretStr | None = None
    live_turn_ttl_seconds: int = Field(default=3600, ge=60, le=86_400)

    refresh_cookie_name: str = "wp_refresh"
    refresh_cookie_secure: bool = True
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    refresh_cookie_domain: str | None = None

    # --- Observability -----------------------------------------------------------
    # Error tracking: exceptions and browser errors go to Sentry when a DSN is set (see app/core/observability.py).
    sentry_dsn: SecretStr | None = None
    sentry_traces_sample_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    # GET /metrics (Prometheus). Served outside /api, so the public proxy never exposes it. When a token is set,
    # scrapers must send "Authorization: Bearer <token>".
    metrics_enabled: bool = True
    metrics_token: SecretStr | None = None
    # The worker has no HTTP API; it serves its metrics on this port (0 = off).
    worker_metrics_port: int = Field(default=9101, ge=0, le=65_535)
    # Browser error reports accepted per client IP per hour (POST /api/client-errors).
    client_errors_per_hour: int = Field(default=60, ge=1, le=10_000)

    # --- E-mail --------------------------------------------------------------
    # `console` writes messages to the log (development only); `smtp` delivers through an SMTP relay or provider.
    email_backend: Literal["console", "smtp"] = "console"
    email_from: str = "WorkPulse <no-reply@workpulse.local>"
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65_535)
    # starttls: upgrade a plain connection (port 587); ssl: TLS from the start (port 465); none: local relays only.
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    smtp_username: str = ""
    smtp_password: SecretStr | None = None
    smtp_timeout_seconds: float = Field(default=15, ge=1, le=120)

    @field_validator("jwt_secret")
    @classmethod
    def _validate_secret_strength(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if len(raw) < 32 or raw.lower() in _WEAK_SECRETS:
            raise ValueError("JWT_SECRET must be a random value of at least 32 characters.")
        return value

    @field_validator(
        "storage_encryption_key",
        "live_turn_secret",
        "anthropic_api_key",
        "redis_url",
        "smtp_password",
        "sentry_dsn",
        "metrics_token",
        mode="before",
    )
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def _check_deployment(self) -> Settings:
        problems = self.configuration_problems()
        if problems:
            raise ValueError("Unsafe configuration:\n- " + "\n- ".join(problems))
        return self

    def configuration_problems(self) -> list[str]:
        """Settings that would break or weaken a deployment. Production refuses to start until they are fixed."""
        problems: list[str] = []
        if not self.background_jobs and self.redis_url is None:
            problems.append(
                "BACKGROUND_JOBS=false needs REDIS_URL: without Redis, events from the worker never reach API processes."
            )
        if bool(self.live_turn_urls.strip()) != (self.live_turn_secret is not None):
            problems.append("LIVE_TURN_URLS and LIVE_TURN_SECRET must be set together.")
        if self.email_backend == "smtp" and not self.smtp_host:
            problems.append("EMAIL_BACKEND=smtp needs SMTP_HOST.")
        if not self.is_production:
            return problems
        if self.debug:
            problems.append("DEBUG must be false in production.")
        if not self.frontend_url.startswith("https://"):
            problems.append("FRONTEND_URL must be an https:// address in production.")
        if not self.refresh_cookie_secure:
            problems.append(
                "REFRESH_COOKIE_SECURE must be true in production (the sign-in cookie needs HTTPS)."
            )
        if "*" in self.cors_origin_list:
            problems.append("CORS_ORIGINS must list origins explicitly in production, not '*'.")
        if self.email_backend == "console":
            problems.append(
                "EMAIL_BACKEND=console writes sign-in links to the log; configure EMAIL_BACKEND=smtp in production."
            )
        if self.storage_encryption_key is None:
            problems.append(
                "STORAGE_ENCRYPTION_KEY must be set in production: otherwise the screenshot key is derived from "
                "JWT_SECRET, and rotating that secret would make every stored screenshot unreadable."
            )
        if self.redis_url is None:
            problems.append("REDIS_URL must be set in production (realtime events across API processes).")
        if self.smtp_security == "none" and self.email_backend == "smtp" and self.smtp_username:
            problems.append("SMTP_SECURITY=none would send the SMTP password unencrypted.")
        return problems

    @field_validator("api_prefix")
    @classmethod
    def _normalise_prefix(cls, value: str) -> str:
        return "/" + value.strip("/") if value.strip("/") else ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def refresh_cookie_path(self) -> str:
        return f"{self.api_prefix}/auth"


@lru_cache
def get_settings() -> Settings:
    return Settings()
