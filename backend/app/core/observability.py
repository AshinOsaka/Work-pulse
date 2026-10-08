"""Metrics and error tracking.

**Metrics** (Prometheus format). API processes serve them at `GET /metrics`, outside `/api`, so the public reverse
proxy (which only forwards `/api/`) never exposes them; scrape `backend:8000/metrics` on the internal network. The
worker serves its own on `WORKER_METRICS_PORT`. With several uvicorn processes in one container, set
`PROMETHEUS_MULTIPROC_DIR` (the Docker image does) so one scrape sums every process.

**Error tracking hooks.** Every ERROR log record that carries an exception (unhandled request errors, background job
failures, WebSocket errors) and every browser error report goes to the registered `ErrorReporter`s. Sentry is built in
and switched on by `SENTRY_DSN`; anything else plugs in with `register_error_reporter`. Reporters never receive request
bodies, cookies or headers.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any, Protocol

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
    start_http_server,
)

from app import __version__
from app.core.config import Settings

logger = logging.getLogger(__name__)

_MULTIPROC = bool(os.environ.get("PROMETHEUS_MULTIPROC_DIR"))
if _MULTIPROC:
    # Must exist before the first metric is created (the API's start command also empties it per start).
    os.makedirs(os.environ["PROMETHEUS_MULTIPROC_DIR"], exist_ok=True)

HTTP_REQUESTS = Counter(
    "workpulse_http_requests_total", "HTTP requests handled", ["method", "route", "status"]
)
HTTP_DURATION = Histogram(
    "workpulse_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
WEBSOCKETS = Gauge(
    "workpulse_websocket_connections",
    "Open WebSocket connections",
    ["channel"],
    multiprocess_mode="livesum",
)
WEBSOCKET_SESSIONS = Counter(
    "workpulse_websocket_sessions_total", "WebSocket connections accepted", ["channel"]
)
ERRORS = Counter("workpulse_errors_total", "Errors logged, by component", ["component"])
CLIENT_ERRORS = Counter("workpulse_client_errors_total", "Errors reported by browsers", ["kind"])
EMAILS = Counter("workpulse_emails_total", "E-mails sent", ["backend", "outcome"])
BUILD_INFO = Gauge(
    "workpulse_build_info", "Build information", ["version", "environment"], multiprocess_mode="liveall"
)


def websocket_channel(path: str) -> str:
    if path.endswith("/agent/live"):
        return "agent_live"
    if "/live/sessions/" in path or "/live/signaling/" in path:
        return "live_viewer"
    if path.endswith("/ws"):
        return "app"
    return "other"


def render_metrics() -> tuple[bytes, str]:
    if _MULTIPROC:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
        return generate_latest(registry), CONTENT_TYPE_LATEST
    return generate_latest(), CONTENT_TYPE_LATEST


def start_metrics_server(port: int) -> None:
    """For processes without an HTTP API (the worker): a small metrics-only HTTP server on its own thread."""
    registry = REGISTRY
    if _MULTIPROC:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
    start_http_server(port, registry=registry)
    logger.info("Metrics served on port %d", port)


# --- Error tracking ------------------------------------------------------------------------------------------------


class ErrorReporter(Protocol):
    def capture_exception(self, exc: BaseException, context: dict[str, Any]) -> None: ...

    def capture_message(self, message: str, context: dict[str, Any]) -> None: ...


_reporters: list[ErrorReporter] = []


def register_error_reporter(reporter: ErrorReporter) -> None:
    _reporters.append(reporter)


def clear_error_reporters() -> None:
    _reporters.clear()


def _each(call: Callable[[ErrorReporter], None]) -> None:
    for reporter in list(_reporters):
        try:
            call(reporter)
        except Exception:  # a broken reporter must never break the app, or log recursively
            logging.getLogger("workpulse.observability").debug("Error reporter failed", exc_info=False)


def report_exception(exc: BaseException, **context: Any) -> None:
    _each(lambda r: r.capture_exception(exc, context))


def report_message(message: str, **context: Any) -> None:
    _each(lambda r: r.capture_message(message, context))


class ErrorTrackingHandler(logging.Handler):
    """Counts ERROR records by component and forwards their exceptions to the reporters."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("workpulse.observability"):
            return
        component = record.name.split(".")[2] if record.name.startswith("app.services.") else record.name
        ERRORS.labels(component=component[:60]).inc()
        if record.exc_info and record.exc_info[1] is not None:
            context = {
                "logger": record.name,
                "message": record.getMessage(),
                "request_id": getattr(record, "request_id", "-"),
            }
            report_exception(record.exc_info[1], **context)


class SentryReporter:
    def __init__(self, sentry: Any) -> None:
        self._sentry = sentry

    def capture_exception(self, exc: BaseException, context: dict[str, Any]) -> None:
        with self._sentry.new_scope() as scope:
            for key, value in context.items():
                if key in ("logger", "request_id"):
                    scope.set_tag(key, str(value)[:200])
                else:
                    scope.set_extra(key, value)
            scope.capture_exception(exc)

    def capture_message(self, message: str, context: dict[str, Any]) -> None:
        with self._sentry.new_scope() as scope:
            for key, value in context.items():
                scope.set_extra(key, value)
            scope.capture_message(message, level="error")


def init_observability(settings: Settings, component: str) -> None:
    """Called once per process, after logging is configured."""
    BUILD_INFO.labels(version=__version__, environment=settings.environment).set(1)
    root = logging.getLogger()
    if not any(isinstance(h, ErrorTrackingHandler) for h in root.handlers):
        root.addHandler(ErrorTrackingHandler())
    if settings.sentry_dsn is None:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment,
        release=f"workpulse@{__version__}",
        server_name=component,
        send_default_pii=False,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # Exceptions reach Sentry through ErrorTrackingHandler, exactly once; its own integrations would duplicate
        # them (and its request integration would attach headers and bodies).
        default_integrations=False,
        auto_enabling_integrations=False,
        max_breadcrumbs=0,
    )
    register_error_reporter(SentryReporter(sentry_sdk))
    logger.info("Error tracking enabled (Sentry) for %s", component)
