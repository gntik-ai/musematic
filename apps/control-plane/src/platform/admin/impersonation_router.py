from __future__ import annotations

from datetime import datetime
from platform.admin.impersonation_models import ImpersonationSession
from platform.admin.impersonation_service import ImpersonationService
from platform.admin.rbac import require_superadmin
from platform.admin.two_person_auth_service import TwoPersonAuthService
from platform.common.dependencies import get_db
from platform.notifications.dependencies import get_notifications_service
from platform.notifications.service import AlertService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/impersonation", tags=["admin", "impersonation"])


class ImpersonationStartRequest(BaseModel):
    target_user_id: UUID
    justification: str = Field(min_length=20, max_length=2000)


class ImpersonationEndRequest(BaseModel):
    session_id: UUID
    end_reason: str = Field(default="ended_by_admin", max_length=256)


class ImpersonationRead(BaseModel):
    session_id: UUID
    impersonating_user_id: UUID
    effective_user_id: UUID
    justification: str
    started_at: datetime
    expires_at: datetime
    ended_at: datetime | None
    end_reason: str | None


class ImpersonationStartResponse(BaseModel):
    session: ImpersonationRead
    access_token: str


def _read(row: ImpersonationSession) -> ImpersonationRead:
    return ImpersonationRead(
        session_id=row.session_id,
        impersonating_user_id=row.impersonating_user_id,
        effective_user_id=row.effective_user_id,
        justification=row.justification,
        started_at=row.started_at,
        expires_at=row.expires_at,
        ended_at=row.ended_at,
        end_reason=row.end_reason,
    )


def _service(
    request: Request,
    session: AsyncSession,
    notifications: AlertService | None = None,
) -> ImpersonationService:
    two_person_auth = TwoPersonAuthService(session, request.app.state.settings)
    return ImpersonationService(
        session,
        request.app.state.settings,
        two_person_auth,
        notifications,
    )


@router.post("/start", response_model=ImpersonationStartResponse)
async def start_impersonation(
    payload: ImpersonationStartRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db),
    notifications: AlertService = Depends(get_notifications_service),
    two_person_auth_token: str | None = Header(default=None, alias="X-Two-Person-Auth-Token"),
) -> ImpersonationStartResponse:
    row, token = await _service(request, session, notifications).start(
        current_user,
        payload.target_user_id,
        payload.justification,
        two_person_auth_token=two_person_auth_token,
    )
    return ImpersonationStartResponse(session=_read(row), access_token=token)


@router.post("/end", status_code=204)
async def end_impersonation(
    payload: ImpersonationEndRequest,
    request: Request,
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db),
    notifications: AlertService = Depends(get_notifications_service),
) -> None:
    await _service(request, session, notifications).end(payload.session_id, payload.end_reason)


@router.get("/active", response_model=ImpersonationRead | None)
async def active_impersonation(
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db),
) -> ImpersonationRead | None:
    row = await _service(request, session).get_active_session(UUID(str(current_user["sub"])))
    return None if row is None else _read(row)
