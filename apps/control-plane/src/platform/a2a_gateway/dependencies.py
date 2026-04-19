from __future__ import annotations

from platform.a2a_gateway.card_generator import AgentCardGenerator
from platform.a2a_gateway.client_service import A2AGatewayClientService
from platform.a2a_gateway.events import A2AEventPublisher
from platform.a2a_gateway.external_registry import ExternalAgentCardRegistry
from platform.a2a_gateway.mcp_server import MCPServerService
from platform.a2a_gateway.repository import A2AGatewayRepository
from platform.a2a_gateway.server_service import A2AServerService
from platform.a2a_gateway.streaming import A2ASSEStream
from platform.auth.dependencies import get_auth_service
from platform.auth.service import AuthService
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.policies.dependencies import get_tool_gateway_service
from platform.policies.gateway import ToolGatewayService
from platform.policies.repository import PolicyRepository
from platform.policies.sanitizer import OutputSanitizer
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def build_a2a_repository(session: AsyncSession) -> A2AGatewayRepository:
    return A2AGatewayRepository(session)


def build_agent_card_generator() -> AgentCardGenerator:
    return AgentCardGenerator()


def build_a2a_event_publisher(request: Request) -> A2AEventPublisher:
    return A2AEventPublisher(_get_producer(request))


def build_external_registry(
    *,
    session: AsyncSession,
    request: Request,
) -> ExternalAgentCardRegistry:
    return ExternalAgentCardRegistry(
        repository=build_a2a_repository(session),
        redis_client=_get_redis(request),
    )


async def get_a2a_server_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    tool_gateway: ToolGatewayService = Depends(get_tool_gateway_service),
) -> A2AServerService:
    return A2AServerService(
        repository=build_a2a_repository(session),
        settings=_get_settings(request),
        auth_service=auth_service,
        tool_gateway=tool_gateway,
        redis_client=_get_redis(request),
        event_publisher=build_a2a_event_publisher(request),
        card_generator=build_agent_card_generator(),
    )


async def get_a2a_client_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    tool_gateway: ToolGatewayService = Depends(get_tool_gateway_service),
) -> A2AGatewayClientService:
    return A2AGatewayClientService(
        repository=build_a2a_repository(session),
        external_registry=build_external_registry(session=session, request=request),
        tool_gateway=tool_gateway,
        event_publisher=build_a2a_event_publisher(request),
        settings=_get_settings(request),
    )


def get_a2a_stream() -> A2ASSEStream:
    return A2ASSEStream(session_factory=database.AsyncSessionLocal)


async def get_mcp_server_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    tool_gateway: ToolGatewayService = Depends(get_tool_gateway_service),
) -> MCPServerService:
    from platform.mcp.dependencies import build_mcp_service

    mcp_service = build_mcp_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=_get_redis(request),
    )
    return MCPServerService(
        mcp_service=mcp_service,
        tool_gateway_service=tool_gateway,
        sanitizer=OutputSanitizer(PolicyRepository(session)),
        settings=_get_settings(request),
        tool_executor=getattr(request.app.state, "mcp_tool_executor", None),
    )
