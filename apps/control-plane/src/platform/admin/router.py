from __future__ import annotations

from platform.admin.feature_flags_router import router as feature_flags_router
from platform.admin.impersonation_router import router as impersonation_router
from platform.admin.rbac import rate_limit_admin
from platform.admin.settings_router import router as settings_router
from platform.admin.tenant_mode_router import router as tenant_mode_router
from platform.admin.two_person_auth_router import router as two_person_auth_router

from fastapi import APIRouter, Depends

admin_router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(rate_limit_admin)],
)


@admin_router.get("/ping")
async def admin_ping() -> dict[str, str]:
    return {"status": "ok"}


admin_router.include_router(feature_flags_router)
admin_router.include_router(impersonation_router)
admin_router.include_router(settings_router)
admin_router.include_router(tenant_mode_router)
admin_router.include_router(two_person_auth_router)
