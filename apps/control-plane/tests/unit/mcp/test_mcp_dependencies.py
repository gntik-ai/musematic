from __future__ import annotations

from platform.mcp.dependencies import (
    _get_producer,
    _get_redis,
    _get_settings,
    build_mcp_repository,
    build_mcp_service,
    build_mcp_tool_registry,
    get_mcp_service,
    get_mcp_tool_registry,
)
from platform.mcp.repository import MCPRepository
from platform.mcp.service import MCPService
from platform.registry.mcp_registry import MCPToolRegistry

from fastapi import FastAPI, Request
from tests.a2a_gateway_support import ToolGatewayStub
from tests.mcp_support import FakeRedisClient, RecordingProducer, build_settings


class ProducerStub(RecordingProducer):
    pass


def _request() -> Request:
    app = FastAPI()
    app.state.settings = build_settings()
    app.state.clients = {"kafka": ProducerStub(), "redis": FakeRedisClient()}
    return Request({"type": "http", "app": app, "headers": []})


def test_dependency_helpers_build_from_app_state() -> None:
    request = _request()
    session = object()

    assert _get_settings(request) is request.app.state.settings
    assert _get_producer(request) is request.app.state.clients["kafka"]
    assert _get_redis(request) is request.app.state.clients["redis"]
    assert isinstance(build_mcp_repository(session), MCPRepository)


async def test_dependency_resolvers_construct_service_and_registry() -> None:
    request = _request()
    session = object()
    service = build_mcp_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=_get_redis(request),
    )

    registry = build_mcp_tool_registry(
        mcp_service=service,
        settings=_get_settings(request),
        redis_client=_get_redis(request),
        tool_gateway=ToolGatewayStub(),
    )
    resolved_service = await get_mcp_service(request, session=session)
    resolved_registry = await get_mcp_tool_registry(
        request,
        mcp_service=resolved_service,
        tool_gateway=ToolGatewayStub(),
    )

    assert isinstance(service, MCPService)
    assert isinstance(registry, MCPToolRegistry)
    assert service.tool_registry is registry
    assert isinstance(resolved_service, MCPService)
    assert isinstance(resolved_registry, MCPToolRegistry)
    assert resolved_service.tool_registry is resolved_registry
