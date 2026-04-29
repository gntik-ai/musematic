from __future__ import annotations

from platform.auth.session import RedisSessionStore
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import settings as default_settings
from uuid import UUID

from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_READ_ONLY_TOGGLE_PATH = "/api/v1/admin/sessions/me/read-only-mode"


class AdminReadOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if (
            not request.url.path.startswith("/api/v1/admin/")
            or request.method in _READ_METHODS
            or _is_read_only_toggle(request)
        ):
            return await call_next(request)
        if await _admin_read_only_mode(request):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "error_code": "admin_read_only_mode",
                        "message": "This admin session is in read-only mode",
                        "suggested_action": "Disable read-only mode after MFA step-up.",
                        "correlation_id": getattr(request.state, "correlation_id", None),
                    }
                },
            )
        return await call_next(request)


async def _admin_read_only_mode(request: Request) -> bool:
    current_user = getattr(request.state, "user", None)
    if not isinstance(current_user, dict):
        return False
    if _truthy(current_user.get("admin_read_only_mode")):
        return True
    user_id = _uuid_or_none(current_user.get("sub"))
    session_id = _uuid_or_none(current_user.get("session_id"))
    if user_id is None or session_id is None:
        return False
    redis_value = await _redis_admin_read_only_mode(request, user_id, session_id)
    if redis_value is not None:
        return redis_value
    async with database.AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT admin_read_only_mode
                FROM sessions
                WHERE id = :session_id
                  AND user_id = :user_id
                  AND revoked_at IS NULL
                  AND expires_at > now()
                LIMIT 1
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        )
        value = result.scalar_one_or_none()
    return bool(value)


async def _redis_admin_read_only_mode(
    request: Request,
    user_id: UUID,
    session_id: UUID,
) -> bool | None:
    if "app" not in request.scope:
        return None
    clients = getattr(request.app.state, "clients", {})
    redis_client = clients.get("redis") if isinstance(clients, dict) else None
    if not isinstance(redis_client, AsyncRedisClient):
        return None
    settings = getattr(request.app.state, "settings", default_settings)
    session_data = await RedisSessionStore(redis_client, settings.auth).get_session(
        user_id,
        session_id,
    )
    if session_data is None:
        return None
    return bool(session_data.get("admin_read_only_mode"))


def _uuid_or_none(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _is_read_only_toggle(request: Request) -> bool:
    return (
        request.method.casefold() == "patch"
        and request.url.path.rstrip("/") == _READ_ONLY_TOGGLE_PATH
    )
