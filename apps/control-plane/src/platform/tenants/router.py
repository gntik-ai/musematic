from __future__ import annotations

from platform.common.tenant_context import TenantContext
from platform.tenants.schemas import TenantBranding, TenantPublic

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/v1/me", tags=["tenants"])


@router.get("/tenant", response_model=TenantPublic)
async def get_request_tenant(request: Request) -> TenantPublic:
    tenant = request.state.tenant
    if not isinstance(tenant, TenantContext):
        raise RuntimeError("Tenant context was not attached to the request.")
    return TenantPublic(
        id=tenant.id,
        slug=tenant.slug,
        kind=tenant.kind,
        subdomain=tenant.subdomain,
        status=tenant.status,
        region=tenant.region,
        display_name=str(
            tenant.branding.get("display_name_override")
            or ("Musematic" if tenant.kind == "default" else tenant.slug)
        ),
        branding=TenantBranding.model_validate(dict(tenant.branding)),
    )
