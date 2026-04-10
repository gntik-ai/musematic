from __future__ import annotations

from collections.abc import AsyncGenerator
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.database import AsyncSessionLocal
from platform.common.exceptions import AuthorizationError, NotFoundError
from typing import Any, cast

import jwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session = AsyncSessionLocal()
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
            settings.auth.jwt_secret_key,
            algorithms=[settings.auth.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthorizationError("TOKEN_EXPIRED", "Authentication token expired") from exc
    except jwt.PyJWTError as exc:
        raise AuthorizationError("UNAUTHORIZED", "Invalid authentication token") from exc
    if not isinstance(payload, dict):
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
