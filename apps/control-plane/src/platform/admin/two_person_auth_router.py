from __future__ import annotations

from datetime import datetime
from platform.admin.rbac import is_superadmin, require_admin, require_superadmin
from platform.admin.two_person_auth_models import TwoPersonAuthRequest
from platform.admin.two_person_auth_service import TwoPersonAuthService
from platform.common.dependencies import get_db
from platform.common.exceptions import AuthorizationError
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/2pa", tags=["admin", "two-person-auth"])


class TwoPersonAuthInitiateRequest(BaseModel):
    action: str = Field(min_length=1, max_length=160)
    payload: dict[str, object] = Field(default_factory=dict)


class TwoPersonAuthRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=512)


class TwoPersonAuthRead(BaseModel):
    request_id: UUID
    action: str
    payload: dict[str, object]
    initiator_id: UUID
    created_at: datetime
    expires_at: datetime
    approved_by_id: UUID | None
    approved_at: datetime | None
    rejected_by_id: UUID | None
    rejected_at: datetime | None
    rejection_reason: str | None
    consumed: bool


class TwoPersonAuthApproveResponse(BaseModel):
    token: str


def _read(row: TwoPersonAuthRequest) -> TwoPersonAuthRead:
    return TwoPersonAuthRead(
        request_id=row.request_id,
        action=row.action,
        payload=row.payload,
        initiator_id=row.initiator_id,
        created_at=row.created_at,
        expires_at=row.expires_at,
        approved_by_id=row.approved_by_id,
        approved_at=row.approved_at,
        rejected_by_id=row.rejected_by_id,
        rejected_at=row.rejected_at,
        rejection_reason=row.rejection_reason,
        consumed=row.consumed,
    )


def _service(request: Request, session: AsyncSession) -> TwoPersonAuthService:
    return TwoPersonAuthService(session, request.app.state.settings)


@router.post("/requests", response_model=TwoPersonAuthRead)
async def initiate_request(
    payload: TwoPersonAuthInitiateRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> TwoPersonAuthRead:
    if payload.action.startswith("multi_region_ops.failover") and not is_superadmin(current_user):
        raise AuthorizationError("SUPERADMIN_REQUIRED", "Failover 2PA requires super admin")
    row = await _service(request, session).initiate(payload.action, payload.payload, current_user)
    return _read(row)


@router.post("/requests/{request_id}/approve", response_model=TwoPersonAuthApproveResponse)
async def approve_request(
    request_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db),
) -> TwoPersonAuthApproveResponse:
    token = await _service(request, session).approve(request_id, current_user)
    return TwoPersonAuthApproveResponse(token=token)


@router.post("/requests/{request_id}/reject", status_code=204)
async def reject_request(
    request_id: UUID,
    payload: TwoPersonAuthRejectRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db),
) -> None:
    await _service(request, session).reject(request_id, current_user, payload.reason)


@router.get("/requests", response_model=list[TwoPersonAuthRead])
async def list_pending_requests(
    request: Request,
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db),
) -> list[TwoPersonAuthRead]:
    return [_read(row) for row in await _service(request, session).list_pending()]


@router.get("/requests/{request_id}", response_model=TwoPersonAuthRead)
async def get_request(
    request_id: UUID,
    request: Request,
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db),
) -> TwoPersonAuthRead:
    return _read(await _service(request, session).get(request_id))
