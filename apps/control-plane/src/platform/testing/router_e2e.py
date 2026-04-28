from __future__ import annotations

from datetime import UTC, datetime
from platform.auth.password import hash_password
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user, get_db
from platform.common.exceptions import AuthorizationError
from platform.testing.schemas_e2e import (
    ChaosKillPodRequest,
    ChaosKillPodResponse,
    ChaosPartitionRequest,
    ChaosPartitionResponse,
    E2EUserProvisionRequest,
    E2EUserProvisionResponse,
    KafkaEventsResponse,
    MockLLMCallsResponse,
    MockLLMClearRequest,
    MockLLMSetRequest,
    MockLLMSetResponse,
    ResetRequest,
    ResetResponse,
    SeedRequest,
    SeedResponse,
)
from platform.testing.service_e2e import (
    ChaosService,
    KafkaObserver,
    ResetService,
    SeedService,
    build_mock_llm_service,
)
from typing import Any, cast

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/_e2e", tags=["_e2e"])


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    return {
        str(item.get("role"))
        for item in roles
        if isinstance(item, dict) and item.get("role") is not None
    }


def _scopes(current_user: dict[str, Any]) -> set[str]:
    scopes = current_user.get("scopes", [])
    if isinstance(scopes, str):
        return {item for item in scopes.split() if item}
    if isinstance(scopes, list):
        return {str(item) for item in scopes}
    return set()


def require_admin_or_e2e_scope(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    role_names = _role_names(current_user)
    if {"platform_admin", "superadmin"} & role_names:
        return current_user
    if "e2e" in _scopes(current_user):
        return current_user
    raise AuthorizationError(
        "PERMISSION_DENIED",
        "Admin role or e2e scope required",
    )


def _settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _redis(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


@router.post("/seed", response_model=SeedResponse)
async def seed(
    payload: SeedRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> SeedResponse:
    del request, current_user
    return await SeedService().seed(payload.scope)


@router.post("/reset", response_model=ResetResponse)
async def reset(
    payload: ResetRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> ResetResponse:
    del request, current_user
    return await ResetService().reset(
        payload.scope,
        include_baseline=payload.include_baseline,
    )


@router.post("/users", response_model=E2EUserProvisionResponse)
async def provision_user(
    payload: E2EUserProvisionRequest,
    session: AsyncSession = Depends(get_db),
) -> E2EUserProvisionResponse:
    display_name = payload.display_name or payload.email.split("@", 1)[0]
    await session.execute(
        text(
            """
            INSERT INTO users (id, email, display_name, status)
            VALUES (:id, :email, :display_name, :status)
            ON CONFLICT (id) DO UPDATE SET
                email = EXCLUDED.email,
                display_name = EXCLUDED.display_name,
                status = EXCLUDED.status,
                updated_at = now()
            """
        ),
        {
            "id": str(payload.id),
            "email": payload.email,
            "display_name": display_name,
            "status": payload.status,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO accounts_users (id, email, display_name, status, signup_source)
            VALUES (:id, :email, :display_name, :status, 'self_registration')
            ON CONFLICT (email) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                status = EXCLUDED.status,
                updated_at = now()
            """
        ),
        {
            "id": str(payload.id),
            "email": payload.email,
            "display_name": display_name,
            "status": payload.status,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO user_credentials (user_id, email, password_hash, is_active)
            VALUES (:id, :email, :password_hash, true)
            ON CONFLICT (user_id) DO UPDATE SET
                email = EXCLUDED.email,
                password_hash = EXCLUDED.password_hash,
                is_active = true,
                updated_at = now()
            """
        ),
        {
            "id": str(payload.id),
            "email": payload.email,
            "password_hash": hash_password(payload.password),
        },
    )
    for role in payload.roles:
        await session.execute(
            text(
                """
                INSERT INTO user_roles (user_id, role, workspace_id)
                SELECT CAST(:id AS uuid), CAST(:role AS varchar), CAST(NULL AS uuid)
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM user_roles
                    WHERE user_id = CAST(:id AS uuid)
                      AND role = CAST(:role AS varchar)
                      AND workspace_id IS NULL
                )
                """
            ),
            {"id": str(payload.id), "role": role},
        )
    return E2EUserProvisionResponse(id=payload.id, email=payload.email, status=payload.status)


@router.post("/chaos/kill-pod", response_model=ChaosKillPodResponse)
async def kill_pod(
    payload: ChaosKillPodRequest,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> ChaosKillPodResponse:
    del current_user
    return await ChaosService().kill_pod(
        payload.namespace,
        payload.label_selector,
        payload.count,
    )


@router.post("/chaos/partition-network", response_model=ChaosPartitionResponse)
async def partition_network(
    payload: ChaosPartitionRequest,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> ChaosPartitionResponse:
    del current_user
    return await ChaosService().partition_network(
        payload.from_namespace,
        payload.to_namespace,
        payload.ttl_seconds,
    )


@router.post("/mock-llm/set-response", response_model=MockLLMSetResponse)
async def set_mock_llm_response(
    payload: MockLLMSetRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> MockLLMSetResponse:
    del current_user
    service = build_mock_llm_service(_redis(request))
    queue_depth = await service.set_response(
        payload.prompt_pattern,
        payload.response,
        payload.streaming_chunks,
    )
    return MockLLMSetResponse(queue_depth=queue_depth)


@router.get("/mock-llm/calls", response_model=MockLLMCallsResponse)
async def get_mock_llm_calls(
    request: Request,
    pattern: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> MockLLMCallsResponse:
    del current_user
    service = build_mock_llm_service(_redis(request))
    records = await service.get_calls(
        pattern=pattern,
        since=since.isoformat() if since else None,
    )
    return MockLLMCallsResponse(calls=records)


@router.post("/mock-llm/clear", status_code=204)
async def clear_mock_llm(
    payload: MockLLMClearRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> None:
    del current_user
    service = build_mock_llm_service(_redis(request))
    await service.clear_queue(payload.prompt_pattern)


@router.get("/kafka/events", response_model=KafkaEventsResponse)
async def kafka_events(
    request: Request,
    topic: str = Query(...),
    since: datetime = Query(...),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    key: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(require_admin_or_e2e_scope),
) -> KafkaEventsResponse:
    del current_user
    observer = KafkaObserver(_settings(request))
    resolved_until = until or datetime.now(UTC)
    return await observer.get_events(
        topic=topic,
        since=since,
        until=resolved_until,
        limit=limit,
        key=key,
    )
