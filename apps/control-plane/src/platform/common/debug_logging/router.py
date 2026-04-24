from __future__ import annotations

from platform.common.debug_logging.models import DebugLoggingCapture, DebugLoggingSession
from platform.common.debug_logging.repository import DebugLoggingRepository
from platform.common.debug_logging.schemas import (
    DebugLoggingCaptureListResponse,
    DebugLoggingCaptureResponse,
    DebugLoggingSessionCreateRequest,
    DebugLoggingSessionListResponse,
    DebugLoggingSessionResponse,
)
from platform.common.debug_logging.service import DebugLoggingService
from platform.common.dependencies import get_current_user, get_db
from platform.common.exceptions import AuthorizationError, PlatformError, ValidationError
from typing import ClassVar
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/admin/debug-logging", tags=["admin", "debug-logging"])


class DebugLoggingMethodNotAllowedError(PlatformError):
    status_code = 405


class _SessionReadAuth:
    accepted: ClassVar[frozenset[str]] = frozenset({"platform_admin", "auditor", "superadmin"})


class _SessionWriteAuth:
    accepted: ClassVar[frozenset[str]] = frozenset({"platform_admin", "superadmin"})


def _role_names(current_user: dict[str, object]) -> set[str]:
    roles_obj = current_user.get("roles")
    if not isinstance(roles_obj, list):
        return set()
    return {str(item.get("role")) for item in roles_obj if isinstance(item, dict)}


def _require_read_access(current_user: dict[str, object]) -> None:
    if _role_names(current_user) & _SessionReadAuth.accepted:
        return
    raise AuthorizationError("PERMISSION_DENIED", "Debug logging read access required")


def _require_write_access(current_user: dict[str, object]) -> None:
    if _role_names(current_user) & _SessionWriteAuth.accepted:
        return
    raise AuthorizationError("PERMISSION_DENIED", "Debug logging admin access required")


def _actor_id(current_user: dict[str, object]) -> UUID:
    try:
        return UUID(str(current_user["sub"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("UNAUTHORIZED", "Missing or invalid subject claim") from exc


def _is_superadmin(current_user: dict[str, object]) -> bool:
    return "superadmin" in _role_names(current_user)


def _correlation_id(request: Request) -> UUID:
    raw = getattr(request.state, "correlation_id", None)
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return UUID(int=0)


def _build_service(request: Request, db: AsyncSession) -> DebugLoggingService:
    return DebugLoggingService(
        repository=DebugLoggingRepository(db),
        redis_client=request.app.state.clients["redis"],
        settings=request.app.state.settings,
        producer=request.app.state.clients.get("kafka"),
    )


async def get_debug_logging_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> DebugLoggingService:
    return _build_service(request, db)


def _session_response(item: DebugLoggingSession) -> DebugLoggingSessionResponse:
    return DebugLoggingSessionResponse(
        session_id=item.id,
        target_type=item.target_type,
        target_id=item.target_id,
        justification=item.justification,
        started_at=item.started_at,
        expires_at=item.expires_at,
        terminated_at=item.terminated_at,
        termination_reason=item.termination_reason,
        capture_count=item.capture_count,
        requested_by=item.requested_by,
        correlation_id=item.correlation_id,
    )


def _capture_response(item: DebugLoggingCapture) -> DebugLoggingCaptureResponse:
    return DebugLoggingCaptureResponse.model_validate(item)


@router.post(
    "/sessions",
    response_model=DebugLoggingSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def open_debug_logging_session(
    payload: DebugLoggingSessionCreateRequest,
    request: Request,
    current_user: dict[str, object] = Depends(get_current_user),
    service: DebugLoggingService = Depends(get_debug_logging_service),
) -> DebugLoggingSessionResponse:
    _require_write_access(current_user)
    session = await service.open_session(
        target_type=payload.target_type.value,
        target_id=payload.target_id,
        justification=payload.justification,
        duration_minutes=payload.duration_minutes,
        requested_by=_actor_id(current_user),
        correlation_id=_correlation_id(request),
    )
    return _session_response(session)


@router.get("/sessions", response_model=DebugLoggingSessionListResponse)
async def list_debug_logging_sessions(
    active_only: bool = Query(default=False),
    requested_by: UUID | None = Query(default=None),
    target_type: str | None = Query(default=None),
    target_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    current_user: dict[str, object] = Depends(get_current_user),
    service: DebugLoggingService = Depends(get_debug_logging_service),
) -> DebugLoggingSessionListResponse:
    _require_read_access(current_user)
    items, next_cursor = await service.list_sessions(
        active_only=active_only,
        requested_by=requested_by,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
        cursor=cursor,
    )
    return DebugLoggingSessionListResponse(
        items=[_session_response(item) for item in items],
        next_cursor=next_cursor,
    )


@router.get("/sessions/{session_id}", response_model=DebugLoggingSessionResponse)
async def get_debug_logging_session(
    session_id: UUID,
    current_user: dict[str, object] = Depends(get_current_user),
    service: DebugLoggingService = Depends(get_debug_logging_service),
) -> DebugLoggingSessionResponse:
    _require_read_access(current_user)
    return _session_response(await service.get_session(session_id))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def terminate_debug_logging_session(
    session_id: UUID,
    current_user: dict[str, object] = Depends(get_current_user),
    service: DebugLoggingService = Depends(get_debug_logging_service),
) -> Response:
    _require_write_access(current_user)
    await service.terminate_session(
        session_id,
        actor_id=_actor_id(current_user),
        is_superadmin=_is_superadmin(current_user),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/sessions/{session_id}/captures",
    response_model=DebugLoggingCaptureListResponse,
)
async def list_debug_logging_captures(
    session_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    cursor: str | None = Query(default=None),
    current_user: dict[str, object] = Depends(get_current_user),
    service: DebugLoggingService = Depends(get_debug_logging_service),
) -> DebugLoggingCaptureListResponse:
    _require_read_access(current_user)
    items, next_cursor = await service.list_captures(session_id, limit=limit, cursor=cursor)
    return DebugLoggingCaptureListResponse(
        items=[_capture_response(item) for item in items],
        next_cursor=next_cursor,
    )


@router.patch("/sessions/{session_id}")
async def patch_debug_logging_session(
    session_id: UUID,
    current_user: dict[str, object] = Depends(get_current_user),
) -> JSONResponse:
    del session_id
    _require_write_access(current_user)
    raise DebugLoggingMethodNotAllowedError(
        "DEBUG_LOGGING_SESSION_EXTENSION_NOT_ALLOWED",
        "Session expiry cannot be extended; open a new session instead",
    )
