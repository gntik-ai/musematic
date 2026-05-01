from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from platform.auth.repository import AuthRepository
from platform.auth.service import AuthService
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.logging import configure_logging
from platform.common.middleware.correlation_logging_middleware import CorrelationLoggingMiddleware
from platform.common.telemetry import setup_telemetry
from platform.tenants.resolver import TenantResolver
from platform.workspaces.dependencies import build_workspaces_service
from platform.ws_hub.connection import ConnectionRegistry
from platform.ws_hub.fanout import KafkaFanout
from platform.ws_hub.router import router as ws_router
from platform.ws_hub.subscription import SubscriptionRegistry
from platform.ws_hub.visibility import VisibilityFilter
from typing import Any, cast

from fastapi import FastAPI


class _NullRedisClient:
    async def _get_client(self) -> _NullRedisClient:
        return self

    async def connect(self) -> None:
        return None

    async def close(self) -> None:
        return None


def _resolve_settings(settings: PlatformSettings | None) -> PlatformSettings:
    resolved = settings or default_settings
    if resolved.profile != "ws-hub":
        resolved = resolved.model_copy(update={"profile": "ws-hub"})
    return resolved


def _create_auth_service_factory(
    app: FastAPI,
) -> Callable[[], AbstractAsyncContextManager[AuthService]]:
    @asynccontextmanager
    async def factory() -> AsyncIterator[AuthService]:
        async with database.AsyncSessionLocal() as session:
            yield AuthService(
                repository=AuthRepository(session),
                redis_client=cast(Any, _NullRedisClient()),
                settings=app.state.settings,
                producer=None,
            )

    return factory


def _create_workspaces_service_factory(
    app: FastAPI,
) -> Callable[[], AbstractAsyncContextManager[Any]]:
    @asynccontextmanager
    async def factory() -> AsyncIterator[Any]:
        async with database.AsyncSessionLocal() as session:
            yield build_workspaces_service(
                session=session,
                settings=app.state.settings,
                producer=None,
                accounts_service=None,
            )

    return factory


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    await app.state.fanout.start()
    try:
        yield
    finally:
        for conn in app.state.connection_registry.all():
            conn.closed.set()
            try:
                await conn.websocket.close(code=1001, reason="server-shutting-down")
            except Exception:
                continue
        for conn in app.state.connection_registry.all():
            for task in list(conn.tasks):
                task.cancel()
        for conn in app.state.connection_registry.all():
            for task in list(conn.tasks):
                try:
                    await asyncio.wait_for(task, timeout=5)
                except (asyncio.CancelledError, TimeoutError):
                    continue
        await app.state.fanout.stop()


def create_ws_app(settings: PlatformSettings | None = None) -> FastAPI:
    resolved = _resolve_settings(settings)
    configure_logging("ws", "platform-control")
    database.configure_database(resolved)

    app = FastAPI(lifespan=_lifespan)
    app.state.settings = resolved
    app.state.connection_registry = ConnectionRegistry()
    app.state.subscription_registry = SubscriptionRegistry()
    app.state.tenant_resolver = TenantResolver(
        settings=resolved,
        session_factory=database.AsyncSessionLocal,
        redis_client=None,
    )
    app.state.auth_service_factory = _create_auth_service_factory(app)
    app.state.workspaces_service_factory = _create_workspaces_service_factory(app)
    app.state.visibility_filter = VisibilityFilter(
        app.state.workspaces_service_factory,
        allow_unresolved_e2e_resources=resolved.feature_e2e_mode,
    )
    app.state.fanout = KafkaFanout(
        connection_registry=app.state.connection_registry,
        subscription_registry=app.state.subscription_registry,
        settings=resolved,
        visibility_filter=app.state.visibility_filter,
    )
    app.add_middleware(CorrelationLoggingMiddleware)
    app.include_router(ws_router)
    setup_telemetry(
        service_name=f"{resolved.otel.service_name}-ws-hub",
        exporter_endpoint=resolved.otel.exporter_endpoint,
        app=app,
    )
    return app


app = create_ws_app()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001, lifespan="on")


if __name__ == "__main__":
    main()
