from __future__ import annotations

from collections.abc import AsyncGenerator
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.exceptions import AuthorizationError, NotFoundError
from platform.common.logging import configure_logging, get_logger
from typing import TYPE_CHECKING, Any, cast

import jwt
from fastapi import Depends, Request
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
        return state_user

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
    return payload


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
