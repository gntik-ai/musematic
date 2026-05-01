from __future__ import annotations

from platform.admin.rbac import require_superadmin
from platform.audit.repository import AuditChainRepository
from platform.audit.service import AuditChainService
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings
from platform.common.events.producer import EventProducer
from platform.common.exceptions import PlatformError, ValidationError
from platform.tenants.dns_automation import build_dns_automation_client
from platform.tenants.exceptions import TenantNotFoundError
from platform.tenants.models import Tenant
from platform.tenants.repository import TenantsRepository
from platform.tenants.schemas import (
    TenantAdminView,
    TenantBranding,
    TenantCreate,
    TenantListResponse,
    TenantProvisionResponse,
    TenantScheduleDeletion,
    TenantSuspend,
    TenantUpdate,
)
from platform.tenants.service import TENANT_DPA_BUCKET, TenantsService
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/tenants", tags=["admin.tenants"])


class DpaUploadResponse(BaseModel):
    dpa_artifact_id: str


@router.get("", response_model=TenantListResponse)
async def list_tenants(
    kind: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 100,
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> TenantListResponse:
    tenants = await TenantsRepository(session).list_all(
        kind=kind,
        status=status,
        q=q,
        limit=limit,
    )
    return TenantListResponse(items=[_admin_view(tenant) for tenant in tenants])


@router.post("", response_model=TenantProvisionResponse, status_code=201)
async def provision_tenant(
    payload: TenantCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> TenantProvisionResponse:
    service = _service(request, session)
    tenant = await service.provision_enterprise_tenant(current_user, payload)
    return TenantProvisionResponse(
        id=tenant.id,
        slug=tenant.slug,
        subdomain=tenant.subdomain,
        kind=tenant.kind,
        status=tenant.status,
        first_admin_invite_sent_to=payload.first_admin_email,
        dns_records_pending=True,
    )


@router.get("/{tenant_id}", response_model=TenantAdminView)
async def get_tenant(
    tenant_id: str,
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> TenantAdminView:
    tenant = await TenantsRepository(session).get_by_id(_coerce_uuid(tenant_id))
    if tenant is None:
        raise TenantNotFoundError()
    return _admin_view(tenant)


@router.patch("/{tenant_id}", response_model=TenantAdminView)
async def update_tenant(
    tenant_id: str,
    payload: TenantUpdate,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> TenantAdminView:
    tenant = await _service(request, session).update_tenant(
        current_user,
        _coerce_uuid(tenant_id),
        payload,
    )
    return _admin_view(tenant)


@router.post("/{tenant_id}/suspend", response_model=TenantAdminView)
async def suspend_tenant(
    tenant_id: str,
    payload: TenantSuspend,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> TenantAdminView:
    tenant = await _service(request, session).suspend_tenant(
        current_user,
        _coerce_uuid(tenant_id),
        payload.reason,
    )
    return _admin_view(tenant)


@router.post("/{tenant_id}/reactivate", response_model=TenantAdminView)
async def reactivate_tenant(
    tenant_id: str,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> TenantAdminView:
    tenant = await _service(request, session).reactivate_tenant(
        current_user,
        _coerce_uuid(tenant_id),
    )
    return _admin_view(tenant)


@router.post("/{tenant_id}/schedule-deletion", response_model=TenantAdminView)
async def schedule_tenant_deletion(
    tenant_id: str,
    payload: TenantScheduleDeletion,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> TenantAdminView:
    tenant = await _service(request, session).schedule_deletion(
        current_user,
        _coerce_uuid(tenant_id),
        payload,
    )
    return _admin_view(tenant)


@router.post("/{tenant_id}/cancel-deletion", response_model=TenantAdminView)
async def cancel_tenant_deletion(
    tenant_id: str,
    request: Request,
    current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(database.get_session),
) -> TenantAdminView:
    tenant = await _service(request, session).cancel_deletion(
        current_user,
        _coerce_uuid(tenant_id),
    )
    return _admin_view(tenant)


@router.post("/dpa-upload", response_model=DpaUploadResponse)
async def upload_dpa(
    request: Request,
    file: UploadFile = File(...),
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> DpaUploadResponse:
    object_storage = _object_storage(request)
    if object_storage is None:
        raise PlatformError("object_storage_unavailable", "Object storage is not configured.")
    artifact_id = f"{uuid4()}.pdf"
    await object_storage.create_bucket_if_not_exists(TENANT_DPA_BUCKET)
    await object_storage.upload_object(
        TENANT_DPA_BUCKET,
        f"pending/{artifact_id}",
        await file.read(),
        content_type=file.content_type or "application/pdf",
        metadata={"original_filename": file.filename or "dpa.pdf"},
    )
    return DpaUploadResponse(dpa_artifact_id=artifact_id)


def _service(request: Request, session: AsyncSession) -> TenantsService:
    settings = _settings(request)
    clients = getattr(request.app.state, "clients", {})
    producer = clients.get("kafka") if isinstance(clients, dict) else None
    notifications = getattr(request.app.state, "notifications_service", None)
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
        dns_automation=getattr(
            request.app.state,
            "tenant_dns_automation",
            build_dns_automation_client(settings),
        ),
        notifications=notifications,
        object_storage=_object_storage(request),
        redis_client=clients.get("redis") if isinstance(clients, dict) else None,
    )


def _object_storage(request: Request) -> Any | None:
    clients = getattr(request.app.state, "clients", {})
    if isinstance(clients, dict):
        return clients.get("object_storage")
    return None


def _settings(request: Request) -> PlatformSettings:
    value = getattr(request.app.state, "settings", None)
    return value if isinstance(value, PlatformSettings) else default_settings


def _admin_view(tenant: Tenant) -> TenantAdminView:
    return TenantAdminView(
        id=tenant.id,
        slug=tenant.slug,
        kind=tenant.kind,
        subdomain=tenant.subdomain,
        status=tenant.status,
        region=tenant.region,
        display_name=tenant.display_name,
        branding=TenantBranding.model_validate(tenant.branding_config_json or {}),
        scheduled_deletion_at=tenant.scheduled_deletion_at,
        created_at=tenant.created_at,
        data_isolation_mode=tenant.data_isolation_mode,
        subscription_id=tenant.subscription_id,
        dpa_signed_at=tenant.dpa_signed_at,
        dpa_version=tenant.dpa_version,
        dpa_artifact_uri=tenant.dpa_artifact_uri,
        dpa_artifact_sha256=tenant.dpa_artifact_sha256,
        contract_metadata=dict(tenant.contract_metadata_json or {}),
        feature_flags=dict(tenant.feature_flags_json or {}),
    )


def _coerce_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValidationError("bad_tenant_id", "Tenant id must be a UUID.") from exc
