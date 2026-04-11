from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from platform.api.health import router as health_router
from platform.auth.events import register_auth_event_types
from platform.auth.router import router as auth_router
from platform.common import database
from platform.common.auth_middleware import AuthMiddleware
from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.neo4j import AsyncNeo4jClient
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.clients.reasoning_engine import ReasoningEngineClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.clients.sandbox_manager import SandboxManagerClient
from platform.common.clients.simulation_controller import SimulationControllerClient
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.correlation import CorrelationMiddleware
from platform.common.dependencies import get_current_user
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.producer import EventProducer
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.common.telemetry import setup_telemetry
from typing import Any, cast

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import Response
from starlette.requests import Request

LOGGER = logging.getLogger(__name__)


def _build_clients(settings: PlatformSettings) -> dict[str, Any]:
    return {
        "redis": AsyncRedisClient.from_settings(settings),
        "kafka": EventProducer.from_settings(settings),
        "kafka_consumer": EventConsumerManager.from_settings(settings),
        "qdrant": AsyncQdrantClient.from_settings(settings),
        "neo4j": AsyncNeo4jClient.from_settings(settings),
        "clickhouse": AsyncClickHouseClient.from_settings(settings),
        "opensearch": AsyncOpenSearchClient.from_settings(settings),
        "minio": AsyncObjectStorageClient.from_settings(settings),
        "runtime_controller": RuntimeControllerClient.from_settings(settings),
        "reasoning_engine": ReasoningEngineClient.from_settings(settings),
        "sandbox_manager": SandboxManagerClient.from_settings(settings),
        "simulation_controller": SimulationControllerClient.from_settings(settings),
    }


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.started_at = time.monotonic()
    app.state.degraded = False
    startup_errors: dict[str, str] = {}
    register_auth_event_types()

    for name, client in app.state.clients.items():
        if name == "kafka_consumer":
            continue
        try:
            await client.connect()
        except Exception as exc:
            app.state.degraded = True
            startup_errors[name] = str(exc)
            LOGGER.warning("Failed to connect %s during startup: %s", name, exc)

    app.state.startup_errors = startup_errors
    try:
        yield
    finally:
        for client in reversed(list(app.state.clients.values())):
            close = getattr(client, "close", None)
            if close is None:
                continue
            try:
                result = close()
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:
                LOGGER.warning("Failed to close client cleanly: %s", exc)


def create_app(profile: str = "api", settings: PlatformSettings | None = None) -> FastAPI:
    resolved = settings or default_settings
    if resolved.profile != profile:
        resolved = resolved.model_copy(update={"profile": profile})

    database.configure_database(resolved)

    app = FastAPI(lifespan=_lifespan)
    app.state.settings = resolved
    app.state.clients = _build_clients(resolved)
    exception_handler = cast(
        Callable[[Request, Exception], Response | Awaitable[Response]],
        platform_exception_handler,
    )
    app.add_exception_handler(PlatformError, exception_handler)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(CorrelationMiddleware)
    app.include_router(health_router)

    api_router = APIRouter(prefix="/api/v1")

    @api_router.get("/protected")
    async def protected_endpoint(
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        return {"status": "ok", "user": current_user}

    if resolved.profile == "api":
        app.include_router(api_router)
        app.include_router(auth_router)

    setup_telemetry(
        service_name=f"{resolved.otel.service_name}-{resolved.profile}",
        exporter_endpoint=resolved.otel.exporter_endpoint,
        app=app,
        engine=database.engine,
    )
    return app
