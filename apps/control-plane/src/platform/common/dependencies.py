from __future__ import annotations

from collections.abc import AsyncGenerator
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.exceptions import AuthorizationError, NotFoundError
from platform.common.impersonation_context import (
    ImpersonationContext,
    set_impersonation_context,
)
from platform.common.logging import configure_logging, get_logger
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import jwt
from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from platform.evaluation.service_interfaces import EvalSuiteServiceInterface
    from platform.testing.service_interfaces import CoordinationTestServiceInterface

_STRUCTLOG_PROVIDERS: set[tuple[str, str]] = set()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session = database.AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def _resolve_settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, getattr(request.app.state, "settings", default_settings))


async def get_current_user(request: Request) -> dict[str, Any]:
    state_user = getattr(request.state, "user", None)
    if isinstance(state_user, dict):
        return await _with_impersonation_context(request, state_user)

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise AuthorizationError("UNAUTHORIZED", "Missing authentication")

    token = header.removeprefix("Bearer ").strip()
    if not token:
        raise AuthorizationError("UNAUTHORIZED", "Missing authentication")

    settings = _resolve_settings(request)
    try:
        payload = jwt.decode(
            token,
            settings.auth.verification_key,
            algorithms=[settings.auth.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthorizationError("TOKEN_EXPIRED", "Authentication token expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthorizationError("UNAUTHORIZED", "Invalid authentication token") from exc
    if not isinstance(payload, dict):
        raise AuthorizationError("UNAUTHORIZED", "Invalid authentication token")
    if payload.get("type") not in {None, "access"}:
        raise AuthorizationError("UNAUTHORIZED", "Invalid authentication token")
    return await _with_impersonation_context(request, payload)


async def _with_impersonation_context(
    request: Request,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if getattr(request.state, "impersonation_checked", False):
        return payload
    request.state.impersonation_checked = True
    raw_session_id = payload.get("impersonation_session_id")
    if raw_session_id is None:
        set_impersonation_context(None)
        return payload

    try:
        impersonation_session_id = UUID(str(raw_session_id))
    except ValueError:
        raise AuthorizationError("IMPERSONATION_INVALID", "Invalid impersonation session") from None

    async with database.AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    s.session_id,
                    s.impersonating_user_id,
                    s.effective_user_id,
                    u.email
                FROM impersonation_sessions s
                JOIN users u ON u.id = s.effective_user_id
                WHERE s.session_id = :session_id
                  AND s.ended_at IS NULL
                  AND s.expires_at > now()
                  AND u.deleted_at IS NULL
                LIMIT 1
                """
            ),
            {"session_id": impersonation_session_id},
        )
        row = result.mappings().first()
        if row is None:
            raise AuthorizationError("IMPERSONATION_EXPIRED", "Impersonation session is inactive")
        roles_result = await session.execute(
            text(
                """
                SELECT role, workspace_id
                FROM user_roles
                WHERE user_id = :user_id
                ORDER BY role ASC
                """
            ),
            {"user_id": row["effective_user_id"]},
        )
        roles = [
            {
                "role": str(role_row.role),
                "workspace_id": (
                    None if role_row.workspace_id is None else str(role_row.workspace_id)
                ),
            }
            for role_row in roles_result
        ]

    effective_user_id = UUID(str(row["effective_user_id"]))
    impersonation_user_id = UUID(str(row["impersonating_user_id"]))
    set_impersonation_context(
        ImpersonationContext(
            impersonation_session_id=impersonation_session_id,
            impersonation_user_id=impersonation_user_id,
            effective_user_id=effective_user_id,
        )
    )
    request.scope["impersonation_session_id"] = str(impersonation_session_id)
    request.scope["impersonation_user_id"] = str(impersonation_user_id)
    request.scope["effective_user_id"] = str(effective_user_id)

    decorated = dict(payload)
    decorated["sub"] = str(effective_user_id)
    decorated["email"] = str(row["email"])
    decorated["roles"] = roles
    decorated["principal_id"] = str(effective_user_id)
    decorated["impersonation_user_id"] = str(impersonation_user_id)
    decorated["effective_user_id"] = str(effective_user_id)
    request.state.user = decorated
    return decorated


async def get_workspace(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    del db
    workspace_id = request.headers.get("X-Workspace-ID")
    if not workspace_id:
        raise NotFoundError("WORKSPACE_NOT_FOUND", "Missing workspace header")
    return {"workspace_id": workspace_id}


def get_opensearch_client(request: Any) -> Any:
    return request.app.state.clients["opensearch"]


def get_structlog_logger(service_name: str, bounded_context: str) -> Any:
    key = (service_name, bounded_context)
    if key not in _STRUCTLOG_PROVIDERS:
        configure_logging(service_name, bounded_context)
        _STRUCTLOG_PROVIDERS.add(key)
    return get_logger(f"{service_name}.{bounded_context}")


async def get_eval_suite_service_interface(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> EvalSuiteServiceInterface:
    from platform.common.events.producer import EventProducer
    from platform.evaluation.dependencies import build_eval_suite_service
    from platform.evaluation.service_interfaces import EvalSuiteServiceInterface

    return cast(
        EvalSuiteServiceInterface,
        build_eval_suite_service(
            session=session,
            settings=_resolve_settings(request),
            producer=cast(EventProducer | None, request.app.state.clients.get("kafka")),
        ),
    )


async def get_coordination_test_service_interface(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> CoordinationTestServiceInterface:
    from platform.common.clients.object_storage import AsyncObjectStorageClient
    from platform.common.clients.reasoning_engine import ReasoningEngineClient
    from platform.common.clients.redis import AsyncRedisClient
    from platform.common.clients.runtime_controller import RuntimeControllerClient
    from platform.common.events.producer import EventProducer
    from platform.testing.dependencies import build_coordination_service
    from platform.testing.service_interfaces import CoordinationTestServiceInterface

    return cast(
        CoordinationTestServiceInterface,
        build_coordination_service(
            session=session,
            settings=_resolve_settings(request),
            producer=cast(EventProducer | None, request.app.state.clients.get("kafka")),
            redis_client=cast(AsyncRedisClient, request.app.state.clients["redis"]),
            object_storage=cast(
                AsyncObjectStorageClient,
                request.app.state.clients["object_storage"],
            ),
            runtime_controller=cast(
                RuntimeControllerClient | None,
                request.app.state.clients.get("runtime_controller"),
            ),
            reasoning_engine=cast(
                ReasoningEngineClient | None,
                request.app.state.clients.get("reasoning_engine"),
            ),
        ),
    )
