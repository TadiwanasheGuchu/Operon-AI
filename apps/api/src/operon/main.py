"""Operon AI API application factory."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from uuid import UUID

from fastapi import APIRouter, FastAPI

from operon.core.config import Settings, get_settings
from operon.core.crypto import SecretBox
from operon.core.csrf import CsrfMiddleware
from operon.core.db import Database
from operon.core.email import create_email_sender
from operon.core.errors import register_error_handlers
from operon.core.logging import configure_logging, get_logger
from operon.core.redis import create_redis
from operon.core.request_context import RequestContextMiddleware
from operon.core.security import PasswordService
from operon.modules.agents.api import router as agents_router
from operon.modules.agents.service import run_due_agents
from operon.modules.ai.service import ProviderRegistry
from operon.modules.audit.api import router as audit_router
from operon.modules.dashboard.api import router as dashboard_router
from operon.modules.health.api import router as health_router
from operon.modules.identity.api import router as identity_router
from operon.modules.incidents.api import router as incidents_router
from operon.modules.incidents.service import escalate_overdue
from operon.modules.integrations.api import router as integrations_router
from operon.modules.integrations.api import webhooks as webhooks_router
from operon.modules.integrations.dispatch import create_dispatcher
from operon.modules.integrations.sync import SyncRuntime, default_http_factory
from operon.modules.intelligence.api import router as intelligence_router
from operon.modules.intelligence.engine import IntelligenceRuntime, run_detection
from operon.modules.notifications.api import router as notifications_router
from operon.modules.organisations.api import router as organisations_router
from operon.modules.permissions.api import router as permissions_router
from operon.modules.workflows.api import router as workflows_router
from operon.modules.workflows.dispatch import create_workflow_dispatcher
from operon.modules.workflows.engine import WorkflowRuntime
from operon.modules.workflows.engine import sweep as workflow_sweep

API_PREFIX = "/api/v1"


async def _inline_maintenance(
    rt: WorkflowRuntime, providers: ProviderRegistry, interval: int
) -> None:
    """Development stand-in for Temporal timers and the maintenance schedule."""
    log = get_logger("operon.maintenance")
    while True:
        await asyncio.sleep(interval)
        try:
            await escalate_overdue(rt.db)
            await workflow_sweep(rt)
            await run_due_agents(rt.db, providers)
        except Exception:
            log.exception("inline_maintenance_failed")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = get_logger("operon.startup")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.db = Database(settings)
        app.state.redis = create_redis(settings)
        app.state.passwords = PasswordService(settings)
        app.state.secret_box = SecretBox(settings.secret_keys.get_secret_value())
        app.state.mailer = create_email_sender(settings)
        # Tests may pre-set an HTTP factory to talk to protocol test servers.
        factory = getattr(app.state, "http_factory", None) or default_http_factory(settings)
        app.state.sync_runtime = SyncRuntime(
            db=app.state.db, settings=settings, box=app.state.secret_box, http_factory=factory
        )
        # Tests may pre-set fake model providers.
        providers = getattr(app.state, "ai_providers", None) or ProviderRegistry.from_settings(
            settings
        )
        intelligence = IntelligenceRuntime(db=app.state.db, providers=providers)
        app.state.intelligence = intelligence

        async def detect(organisation_id: UUID, trigger: str) -> None:
            await run_detection(intelligence, organisation_id, trigger)

        app.state.sync_runtime.on_data_changed.append(detect)
        app.state.dispatcher = create_dispatcher(app.state.sync_runtime)
        app.state.workflow_runtime = WorkflowRuntime(sync=app.state.sync_runtime)
        app.state.workflow_dispatcher = create_workflow_dispatcher(app.state.workflow_runtime)
        maintenance = None
        if settings.workflow_backend == "inline" and settings.inline_maintenance_interval_seconds:
            maintenance = asyncio.create_task(
                _inline_maintenance(
                    app.state.workflow_runtime,
                    intelligence.providers,
                    settings.inline_maintenance_interval_seconds,
                )
            )
        log.info("startup", environment=settings.environment, version=settings.version)
        try:
            yield
        finally:
            if maintenance is not None:
                maintenance.cancel()
                with suppress(asyncio.CancelledError):
                    await maintenance
            await app.state.redis.aclose()
            await app.state.db.dispose()
            log.info("shutdown")

    app = FastAPI(
        title="Operon AI API",
        version=settings.version,
        lifespan=lifespan,
        # Interactive docs are a development aid; the OpenAPI schema stays available for clients.
        docs_url=None if settings.is_production else f"{API_PREFIX}/docs",
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    # Last added = outermost: request IDs exist before CSRF can reject a request.
    app.add_middleware(CsrfMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    v1 = APIRouter(prefix=API_PREFIX)
    v1.include_router(health_router)
    v1.include_router(identity_router)
    v1.include_router(organisations_router)
    v1.include_router(permissions_router)
    v1.include_router(audit_router)
    v1.include_router(dashboard_router)
    v1.include_router(notifications_router)
    v1.include_router(integrations_router)
    v1.include_router(intelligence_router)
    v1.include_router(incidents_router)
    v1.include_router(workflows_router)
    v1.include_router(agents_router)
    v1.include_router(webhooks_router)
    app.include_router(v1)
    return app
