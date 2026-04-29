from __future__ import annotations

from platform.common.clients.redis import AsyncRedisClient
from platform.common.dependencies import get_current_user
from typing import Any

from fastapi import Depends, HTTPException, Request

ADMIN_ROLES = frozenset({"platform_admin", "superadmin"})
SUPERADMIN_ROLE = "superadmin"
ADMIN_RATE_LIMIT_PER_MINUTE = 600


def _correlation_id(request: Request) -> str | None:
    value = getattr(request.state, "correlation_id", None)
    return str(value) if value else None


def _structured_403(
    request: Request,
    *,
    error_code: str,
    message: str,
    suggested_action: str,
) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "error_code": error_code,
            "message": message,
            "suggested_action": suggested_action,
            "correlation_id": _correlation_id(request),
        },
    )


def role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    if not isinstance(roles, list):
        return set()
    names: set[str] = set()
    for role in roles:
        if isinstance(role, str):
            names.add(role)
        elif isinstance(role, dict) and role.get("role") is not None:
            names.add(str(role["role"]))
    return names


def is_admin(current_user: dict[str, Any]) -> bool:
    return bool(role_names(current_user) & ADMIN_ROLES)


def is_superadmin(current_user: dict[str, Any]) -> bool:
    return SUPERADMIN_ROLE in role_names(current_user)


async def require_admin(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if is_admin(current_user):
        return current_user
    raise _structured_403(
        request,
        error_code="admin_required",
        message="Admin role required",
        suggested_action="Sign in with a platform_admin or superadmin account.",
    )


async def require_superadmin(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if is_superadmin(current_user):
        return current_user
    raise _structured_403(
        request,
        error_code="superadmin_required",
        message="Super admin role required",
        suggested_action="Ask a super admin to perform this action or grant the required role.",
    )


async def rate_limit_admin(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> None:
    clients = getattr(request.app.state, "clients", {})
    redis_client = clients.get("redis") if isinstance(clients, dict) else None
    if not isinstance(redis_client, AsyncRedisClient):
        return
    source_ip = request.client.host if request.client is not None else "unknown"
    principal = str(current_user.get("principal_id") or current_user.get("sub") or source_ip)
    result = await redis_client.check_rate_limit(
        "admin",
        principal,
        ADMIN_RATE_LIMIT_PER_MINUTE,
        60_000,
    )
    if result.allowed:
        return
    raise HTTPException(
        status_code=429,
        detail={
            "error_code": "admin_rate_limit_exceeded",
            "message": "Admin API rate limit exceeded",
            "suggested_action": "Wait before retrying this admin operation.",
            "correlation_id": _correlation_id(request),
        },
        headers={"Retry-After": str(max(1, result.retry_after_ms // 1000))},
    )
