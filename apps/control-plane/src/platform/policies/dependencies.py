from __future__ import annotations

from platform.common.clients.reasoning_engine import ReasoningEngineClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from platform.policies.gateway import MemoryWriteGateService, ToolGatewayService
from platform.policies.repository import PolicyRepository
from platform.policies.sanitizer import OutputSanitizer
from platform.policies.service import PolicyService
from platform.registry.dependencies import get_registry_service
from platform.registry.service import RegistryService
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.service import WorkspacesService
from typing import Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_producer(request: Request) -> EventProducer | None:
    return cast(EventProducer | None, request.app.state.clients.get("kafka"))


def _get_redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def _get_reasoning_client(request: Request) -> ReasoningEngineClient | None:
    return cast(ReasoningEngineClient | None, request.app.state.clients.get("reasoning_engine"))


def build_policy_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
    registry_service: RegistryService | None,
    workspaces_service: WorkspacesService | None,
    reasoning_client: ReasoningEngineClient | None,
) -> PolicyService:
    return PolicyService(
        repository=PolicyRepository(session),
        settings=settings,
        producer=producer,
        redis_client=redis_client,
        registry_service=registry_service,
        workspaces_service=workspaces_service,
        reasoning_client=reasoning_client,
    )


async def get_policy_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    registry_service: RegistryService = Depends(get_registry_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> PolicyService:
    return build_policy_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=_get_redis(request),
        registry_service=registry_service,
        workspaces_service=workspaces_service,
        reasoning_client=_get_reasoning_client(request),
    )


def build_tool_gateway_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
    registry_service: RegistryService | None,
    workspaces_service: WorkspacesService | None,
    reasoning_client: ReasoningEngineClient | None,
) -> ToolGatewayService:
    policy_service = build_policy_service(
        session=session,
        settings=settings,
        producer=producer,
        redis_client=redis_client,
        registry_service=registry_service,
        workspaces_service=workspaces_service,
        reasoning_client=reasoning_client,
    )
    sanitizer = OutputSanitizer(PolicyRepository(session))
    return ToolGatewayService(
        policy_service=policy_service,
        sanitizer=sanitizer,
        reasoning_client=reasoning_client,
        registry_service=registry_service,
        settings=settings,
    )


async def get_tool_gateway_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    registry_service: RegistryService = Depends(get_registry_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> ToolGatewayService:
    return build_tool_gateway_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=_get_redis(request),
        registry_service=registry_service,
        workspaces_service=workspaces_service,
        reasoning_client=_get_reasoning_client(request),
    )


def build_memory_write_gate_service(
    *,
    session: AsyncSession,
    settings: PlatformSettings,
    producer: EventProducer | None,
    redis_client: AsyncRedisClient,
    registry_service: RegistryService | None,
    workspaces_service: WorkspacesService | None,
    reasoning_client: ReasoningEngineClient | None,
    memory_service: Any | None = None,
) -> MemoryWriteGateService:
    policy_service = build_policy_service(
        session=session,
        settings=settings,
        producer=producer,
        redis_client=redis_client,
        registry_service=registry_service,
        workspaces_service=workspaces_service,
        reasoning_client=reasoning_client,
    )
    return MemoryWriteGateService(policy_service=policy_service, memory_service=memory_service)


async def get_memory_write_gate_service(
    request: Request,
    session: AsyncSession = Depends(get_db),
    registry_service: RegistryService = Depends(get_registry_service),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> MemoryWriteGateService:
    return build_memory_write_gate_service(
        session=session,
        settings=_get_settings(request),
        producer=_get_producer(request),
        redis_client=_get_redis(request),
        registry_service=registry_service,
        workspaces_service=workspaces_service,
        reasoning_client=_get_reasoning_client(request),
    )
