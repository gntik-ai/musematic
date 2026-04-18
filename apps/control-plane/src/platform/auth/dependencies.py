from __future__ import annotations

from collections.abc import Callable
from platform.accounts.repository import AccountsRepository
from platform.auth.ibor_service import IBORConnectorService
from platform.auth.ibor_sync import IBORSyncService
from platform.auth.repository import AuthRepository
from platform.auth.service import AuthService
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user, get_db
from platform.common.events.producer import EventProducer
from platform.common.exceptions import AuthorizationError
from typing import Any, cast
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def _get_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)


def _get_redis_client(request: Request) -> AsyncRedisClient:
    return cast(AsyncRedisClient, request.app.state.clients["redis"])


def _get_producer(request: Request) -> EventProducer | None:
    producer = request.app.state.clients.get("kafka")
    return cast(EventProducer | None, producer)


def build_auth_service(request: Request, db: AsyncSession) -> AuthService:
    return AuthService(
        repository=AuthRepository(db),
        redis_client=_get_redis_client(request),
        settings=_get_settings(request),
        producer=_get_producer(request),
    )


def build_ibor_service(request: Request, db: AsyncSession) -> IBORConnectorService:
    del request
    return IBORConnectorService(repository=AuthRepository(db))


def build_ibor_sync_service(request: Request, db: AsyncSession) -> IBORSyncService:
    return IBORSyncService(
        repository=AuthRepository(db),
        accounts_repository=AccountsRepository(db),
        redis_client=_get_redis_client(request),
        settings=_get_settings(request),
        producer=_get_producer(request),
        session_factory=database.AsyncSessionLocal,
    )


async def get_auth_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthService:
    return build_auth_service(request, db)


async def get_ibor_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> IBORConnectorService:
    return build_ibor_service(request, db)


async def get_ibor_sync_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> IBORSyncService:
    return build_ibor_sync_service(request, db)


async def resolve_api_key_identity(
    request: Request,
    raw_key: str,
) -> dict[str, Any] | None:
    async with database.AsyncSessionLocal() as db:
        service = build_auth_service(request, db)
        credential = await service.verify_api_key(raw_key)
        if credential is None:
            return None
        return {
            "sub": str(credential.service_account_id),
            "service_account_id": str(credential.service_account_id),
            "name": credential.name,
            "roles": [
                {
                    "role": credential.role,
                    "workspace_id": (
                        str(credential.workspace_id)
                        if credential.workspace_id is not None
                        else None
                    ),
                }
            ],
            "identity_type": "service_account",
            "workspace_id": (
                str(credential.workspace_id) if credential.workspace_id is not None else None
            ),
        }


def require_permission(resource_type: str, action: str) -> Callable[..., Any]:
    async def dependency(
        request: Request,
        current_user: dict[str, Any] = Depends(get_current_user),
        auth_service: AuthService = Depends(get_auth_service),
    ) -> dict[str, Any]:
        subject = current_user.get("sub")
        if not isinstance(subject, str):
            raise AuthorizationError("UNAUTHORIZED", "Missing subject claim")

        raw_workspace_id = request.headers.get("X-Workspace-ID")
        workspace_id = UUID(raw_workspace_id) if raw_workspace_id else None
        result = await auth_service.check_permission(
            user_id=UUID(subject),
            resource_type=resource_type,
            action=action,
            workspace_id=workspace_id,
            identity_type=str(current_user.get("identity_type", "user")),
            agent_purpose=cast(str | None, current_user.get("agent_purpose")),
        )
        if not result.allowed:
            raise AuthorizationError("PERMISSION_DENIED", result.reason or "Permission denied")
        return current_user

    return dependency
