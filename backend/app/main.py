"""WorkPulse API application factory."""

from __future__ import annotations

import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.core.broker import Broker, build_broker
from app.core.config import Settings, get_settings
from app.core.database import MongoDatabase
from app.core.exceptions import register_exception_handlers
from app.core.keys import url_signing_key
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.object_storage import ObjectStorage, build_object_storage
from app.core.observability import init_observability, render_metrics
from app.core.signed_urls import UrlSigner
from app.core.web_security import BrowserSecurityMiddleware
from app.services.background import BackgroundJobs
from app.services.bootstrap_service import BootstrapService
from app.services.email_service import build_email_sender
from app.services.live_hub import LiveHub
from app.services.notifications.notifier import Notifier, OutboxRepository
from app.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    mongo = MongoDatabase(settings)
    await mongo.connect()
    app.state.mongo = mongo
    await BootstrapService(mongo.db).run()

    if not hasattr(app.state, "email_sender"):
        app.state.email_sender = build_email_sender(settings)
    if not hasattr(app.state, "broker"):
        app.state.broker = build_broker(settings.redis_url.get_secret_value() if settings.redis_url else None)
    broker: Broker = app.state.broker
    await broker.start()
    app.state.ws_manager = ConnectionManager(broker)
    if not hasattr(app.state, "object_storage"):
        app.state.object_storage = build_object_storage(settings)
    storage: ObjectStorage = app.state.object_storage
    app.state.url_signer = UrlSigner(url_signing_key(settings), settings.screenshot_url_ttl_seconds)
    app.state.notifier = notifier = Notifier(mongo.db, broker)
    await OutboxRepository.ensure_indexes(mongo.db)
    notifier.start()
    app.state.live_hub = LiveHub(settings, mongo.db, broker=broker)
    app.state.live_hub.notifier = notifier
    await app.state.live_hub.startup()
    jobs = BackgroundJobs(
        db=mongo.db,
        settings=settings,
        broker=broker,
        storage=storage,
        signer=app.state.url_signer,
        sockets=app.state.ws_manager,
        email=app.state.email_sender,
        notifier=notifier,
    )
    app.state.background = jobs
    app.state.notification_dispatcher = jobs.dispatcher
    app.state.alert_scanner = jobs.scanner
    app.state.report_worker = jobs.reports
    if settings.background_jobs:
        await jobs.start()

    logger.info("%s API v%s started (%s)", settings.app_name, __version__, settings.environment)
    try:
        yield
    finally:
        await app.state.live_hub.shutdown()
        await jobs.stop()
        await notifier.stop()
        await broker.stop()
        await mongo.close()
        logger.info("%s API stopped", settings.app_name)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    init_observability(settings, "api")

    docs_enabled = not settings.is_production
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=__version__,
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url=f"{settings.api_prefix}/openapi.json" if docs_enabled else None,
    )
    app.state.settings = settings

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )
    app.add_middleware(BrowserSecurityMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    if settings.metrics_enabled:
        _add_metrics_route(app, settings)
    return app


def _add_metrics_route(app: FastAPI, settings: Settings) -> None:
    """Prometheus metrics, outside the API prefix: the public proxy only forwards /api/, so this stays internal."""
    token = settings.metrics_token.get_secret_value() if settings.metrics_token else None

    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request) -> Response:
        if token is not None:
            supplied = request.headers.get("authorization", "")
            if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
                return Response(status_code=401, headers={"WWW-Authenticate": "Bearer"})
        body, content_type = render_metrics()
        return Response(body, media_type=content_type, headers={"Cache-Control": "no-store"})


app = create_app()
