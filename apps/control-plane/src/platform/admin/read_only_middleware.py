from __future__ import annotations

from platform.common import database
from uuid import UUID

from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class AdminReadOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if not request.url.path.startswith("/api/v1/admin/") or request.method in _READ_METHODS:
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
    if bool(current_user.get("admin_read_only_mode")):
        return True
    user_id = _uuid_or_none(current_user.get("sub"))
    session_id = _uuid_or_none(current_user.get("session_id"))
    if user_id is None or session_id is None:
        return False
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


def _uuid_or_none(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None
