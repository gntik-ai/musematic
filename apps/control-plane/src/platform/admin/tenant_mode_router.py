from __future__ import annotations

from platform.admin.rbac import require_superadmin
from platform.admin.tenant_mode_service import TenantModeService
from platform.admin.two_person_auth_service import TwoPersonAuthService
from platform.audit.dependencies import get_audit_chain_service
from platform.audit.service import AuditChainService
from platform.common.dependencies import get_db
from platform.common.events.producer import EventProducer
from typing import Any, cast

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/tenant-mode", tags=["admin", "tenant-mode"])


class TenantModeResponse(BaseModel):
    previous_mode: str
    tenant_mode: str
    blocking_tenant_ids: list[str] = []


def _service(
    request: Request,
    session: AsyncSession,
    audit_chain: AuditChainService,
) -> TenantModeService:
    return TenantModeService(
        session,
        TwoPersonAuthService(session, request.app.state.settings),
        audit_chain,
        cast(EventProducer | None, request.app.state.clients.get("kafka")),
    )


@router.post("/upgrade-to-multi", response_model=TenantModeResponse)
async def upgrade_to_multi(
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
    two_person_auth_token: str | None = Header(default=None, alias="X-Two-Person-Auth-Token"),
) -> TenantModeResponse:
    result = await _service(request, session, audit_chain).upgrade_to_multi(
        actor=current_user,
        two_person_auth_token=two_person_auth_token,
    )
    return TenantModeResponse(**result)


@router.post("/downgrade-to-single", response_model=TenantModeResponse)
async def downgrade_to_single(
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
    two_person_auth_token: str | None = Header(default=None, alias="X-Two-Person-Auth-Token"),
) -> TenantModeResponse:
    result = await _service(request, session, audit_chain).downgrade_to_single(
        actor=current_user,
        two_person_auth_token=two_person_auth_token,
    )
    return TenantModeResponse(**result)
