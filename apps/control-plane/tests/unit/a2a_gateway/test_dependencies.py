from __future__ import annotations

from platform.a2a_gateway.card_generator import AgentCardGenerator
from platform.a2a_gateway.client_service import A2AGatewayClientService
from platform.a2a_gateway.dependencies import (
    _get_producer,
    _get_redis,
    _get_settings,
    build_a2a_event_publisher,
    build_a2a_repository,
    build_agent_card_generator,
    build_external_registry,
    get_a2a_client_service,
    get_a2a_server_service,
    get_a2a_stream,
)
from platform.a2a_gateway.events import A2AEventPublisher
from platform.a2a_gateway.external_registry import ExternalAgentCardRegistry
from platform.a2a_gateway.repository import A2AGatewayRepository
from platform.a2a_gateway.server_service import A2AServerService

from fastapi import FastAPI, Request
from tests.a2a_gateway_support import (
    AuthServiceStub,
    FakeRedisClient,
    ToolGatewayStub,
    build_settings,
)


class ProducerStub:
    pass


def _request() -> Request:
    app = FastAPI()
    app.state.settings = build_settings()
    app.state.clients = {"kafka": ProducerStub(), "redis": FakeRedisClient()}
    return Request({"type": "http", "app": app, "headers": []})


def test_dependency_builders_read_app_state() -> None:
    request = _request()
    session = object()

    assert _get_settings(request) is request.app.state.settings
    assert _get_producer(request) is request.app.state.clients["kafka"]
    assert _get_redis(request) is request.app.state.clients["redis"]
    assert isinstance(build_a2a_repository(session), A2AGatewayRepository)
    assert isinstance(build_agent_card_generator(), AgentCardGenerator)
    assert isinstance(build_a2a_event_publisher(request), A2AEventPublisher)
    assert isinstance(
        build_external_registry(session=session, request=request), ExternalAgentCardRegistry
    )


async def test_dependency_resolvers_construct_services() -> None:
    request = _request()
    session = object()
    auth_service = AuthServiceStub()
    tool_gateway = ToolGatewayStub()

    server = await get_a2a_server_service(
        request,
        session=session,
        auth_service=auth_service,
        tool_gateway=tool_gateway,
    )
    client = await get_a2a_client_service(
        request,
        session=session,
        tool_gateway=tool_gateway,
    )
    stream = get_a2a_stream()

    assert isinstance(server, A2AServerService)
    assert isinstance(client, A2AGatewayClientService)
    assert callable(stream.session_factory)
