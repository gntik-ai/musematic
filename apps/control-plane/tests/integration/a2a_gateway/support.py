from __future__ import annotations

from platform.a2a_gateway.client_service import A2AGatewayClientService
from platform.a2a_gateway.dependencies import (
    get_a2a_client_service,
    get_a2a_server_service,
    get_a2a_stream,
)
from platform.a2a_gateway.router import router
from platform.a2a_gateway.server_service import A2AServerService
from platform.a2a_gateway.streaming import A2ASSEStream
from platform.auth.dependencies import get_auth_service
from platform.common.exceptions import PlatformError, platform_exception_handler
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from tests.a2a_gateway_support import (
    AuthServiceStub,
    FakeA2ARepository,
    FakeRedisClient,
    InteractionRepositoryStub,
    RecordingEventPublisher,
    SanitizationStub,
    ToolGatewayStub,
    build_settings,
)


class SessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def build_server_stack(
    *, repo: FakeA2ARepository | None = None, tool_gateway: ToolGatewayStub | None = None
):
    repository = repo or FakeA2ARepository()
    publisher = RecordingEventPublisher()
    interactions = InteractionRepositoryStub()
    service = A2AServerService(
        repository=repository,
        settings=build_settings(),
        auth_service=AuthServiceStub(),
        tool_gateway=tool_gateway
        or ToolGatewayStub(sanitize_result=SanitizationStub(output="clean result")),
        redis_client=FakeRedisClient(),
        event_publisher=publisher,
        card_generator=SimpleNamespace(
            generate_platform_card=AsyncMock(return_value={"name": "mesh", "skills": []})
        ),
    )
    return SimpleNamespace(
        service=service,
        repository=repository,
        publisher=publisher,
        interactions=interactions,
    )


def build_client_stack(
    *,
    repo: FakeA2ARepository | None = None,
    external_registry,
    tool_gateway: ToolGatewayStub | None = None,
    http_client=None,
):
    repository = repo or FakeA2ARepository()
    publisher = RecordingEventPublisher()
    service = A2AGatewayClientService(
        repository=repository,
        external_registry=external_registry,
        tool_gateway=tool_gateway
        or ToolGatewayStub(sanitize_result=SanitizationStub(output="safe result")),
        event_publisher=publisher,
        settings=build_settings(),
        http_client=http_client,
    )
    return SimpleNamespace(service=service, repository=repository, publisher=publisher)


def build_app(
    *,
    auth_service: AuthServiceStub,
    server_service: A2AServerService | None = None,
    client_service: A2AGatewayClientService | None = None,
    stream: A2ASSEStream | None = None,
) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    if server_service is not None:
        app.dependency_overrides[get_a2a_server_service] = lambda: server_service
    if client_service is not None:
        app.dependency_overrides[get_a2a_client_service] = lambda: client_service
    if stream is not None:
        app.dependency_overrides[get_a2a_stream] = lambda: stream
    return app
