from __future__ import annotations

from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.mcp.repository import MCPRepository
from platform.mcp.service import MCPService
from platform.policies.dependencies import get_tool_gateway_service
from platform.policies.gateway import ToolGatewayService
from platform.registry.mcp_registry import MCPToolRegistry
from typing import cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def build_mcp_repository(session: AsyncSession) -> MCPRepository:
    return MCPRepository(session)


def build_mcp_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
) -> MCPService:
    return MCPService(
        repository=MCPRepository(session),
        settings=settings,
        producer=producer,
        redis_client=redis_client,
    )


async def get_mcp_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> MCPService:
    return build_mcp_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=_get_redis(request),
    )


def build_mcp_tool_registry(
    *,
    mcp_service: MCPService,
    settings: PlatformSettings,
    redis_client: AsyncRedisClient,
    tool_gateway: ToolGatewayService | None,
) -> MCPToolRegistry:
    registry = MCPToolRegistry(
        repository=mcp_service.repository,
        mcp_service=mcp_service,
        settings=settings,
        redis_client=redis_client,
        tool_gateway=tool_gateway,
    )
    mcp_service.tool_registry = registry
    return registry


async def get_mcp_tool_registry(
    request: Request,
    mcp_service: MCPService = Depends(get_mcp_service),
    tool_gateway: ToolGatewayService = Depends(get_tool_gateway_service),
) -> MCPToolRegistry:
    return build_mcp_tool_registry(
        mcp_service=mcp_service,
        settings=_get_settings(request),
        redis_client=_get_redis(request),
        tool_gateway=tool_gateway,
    )
