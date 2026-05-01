from __future__ import annotations

from platform.admin.rbac import role_names
from platform.audit.repository import AuditChainRepository
from platform.audit.service import AuditChainService
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.dependencies import get_current_user
from platform.common.events.producer import EventProducer
from platform.tenants.admin_router import _coerce_uuid, _object_storage
from platform.tenants.dns_automation import build_dns_automation_client
from platform.tenants.repository import TenantsRepository
from platform.tenants.service import TenantsService
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/platform/tenants", tags=["platform.tenants"])


class ForceCascadeDeletionRequest(BaseModel):
    two_pa_token: str = Field(min_length=1)
    incident_mode: bool


class ForceCascadeDeletionResponse(BaseModel):
    tenant_id: str
    row_count_digest: dict[str, int]


async def require_platform_staff(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if role_names(current_user) & {"platform_staff"}:
        return current_user
    raise HTTPException(status_code=403, detail={"code": "not_platform_staff"})


@router.post("/{tenant_id}/force-cascade-deletion", response_model=ForceCascadeDeletionResponse)
async def force_cascade_deletion(
    tenant_id: str,
    payload: ForceCascadeDeletionRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(require_platform_staff),
    session: AsyncSession = Depends(database.get_platform_staff_session),
) -> ForceCascadeDeletionResponse:
    if not payload.incident_mode:
        raise HTTPException(status_code=409, detail={"code": "incident_mode_required"})
    service = _service(request, session)
    await service._get_mutable_tenant(_coerce_uuid(tenant_id))
    await service._consume_deletion_two_pa(
        _coerce_uuid(str(current_user.get("sub") or current_user.get("id"))),
        _coerce_uuid(tenant_id),
        payload.two_pa_token,
    )
    row_count_digest = await service.complete_deletion(_coerce_uuid(tenant_id))
    return ForceCascadeDeletionResponse(tenant_id=tenant_id, row_count_digest=row_count_digest)


def _service(request: Request, session: AsyncSession) -> TenantsService:
    settings = _settings(request)
    clients = getattr(request.app.state, "clients", {})
    producer = clients.get("kafka") if isinstance(clients, dict) else None
    return TenantsService(
        session=session,
        repository=TenantsRepository(session),
        settings=settings,
        producer=producer,
        audit_chain=AuditChainService(
            AuditChainRepository(session),
            settings,
            producer=producer if isinstance(producer, EventProducer) else None,
        ),
        dns_automation=build_dns_automation_client(settings),
        notifications=None,
        object_storage=_object_storage(request),
        redis_client=clients.get("redis") if isinstance(clients, dict) else None,
    )


def _settings(request: Request) -> PlatformSettings:
    value = getattr(request.app.state, "settings", None)
    return value if isinstance(value, PlatformSettings) else default_settings
