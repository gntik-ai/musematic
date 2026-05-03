from __future__ import annotations

from platform.accounts.admin_router import router as accounts_admin_router
from platform.admin.config_import_export_router import router as config_import_export_router
from platform.admin.feature_flags_router import router as feature_flags_router
from platform.admin.health_router import router as health_router
from platform.admin.impersonation_router import router as impersonation_router
from platform.admin.lifecycle_router import router as lifecycle_router
from platform.admin.operations_router import router as operations_router
from platform.admin.rbac import rate_limit_admin
from platform.admin.routers.vault import router as vault_admin_router
from platform.admin.settings_router import router as settings_router
from platform.admin.two_person_auth_router import router as two_person_auth_router
from platform.audit.admin_router import router as audit_admin_router
from platform.auth.admin_router import router as auth_admin_router
from platform.connectors.admin_router import router as connectors_admin_router
from platform.cost_governance.admin_router import router as cost_governance_admin_router
from platform.incident_response.admin_router import router as incident_response_admin_router
from platform.marketplace.admin_router import router as marketplace_review_admin_router
from platform.model_catalog.admin_router import router as model_catalog_admin_router
from platform.multi_region_ops.admin_router import router as multi_region_ops_admin_router
from platform.notifications.admin_router import router as notifications_admin_router
from platform.policies.admin_router import router as policies_admin_router
from platform.privacy_compliance.admin_router import router as privacy_compliance_admin_router
from platform.security.abuse_prevention.admin_router import router as abuse_prevention_admin_router
from platform.security_compliance.admin_router import router as security_compliance_admin_router
from platform.tenants.admin_router import router as tenants_admin_router
from platform.workspaces.admin_router import router as workspaces_admin_router

from fastapi import APIRouter, Depends

admin_router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(rate_limit_admin)],
)


@admin_router.get("/ping")
async def admin_ping() -> dict[str, str]:
    return {"status": "ok"}


admin_router.include_router(accounts_admin_router)
admin_router.include_router(audit_admin_router)
admin_router.include_router(auth_admin_router)
admin_router.include_router(config_import_export_router)
admin_router.include_router(connectors_admin_router)
admin_router.include_router(cost_governance_admin_router)
admin_router.include_router(feature_flags_router)
admin_router.include_router(health_router)
admin_router.include_router(impersonation_router)
admin_router.include_router(incident_response_admin_router)
admin_router.include_router(lifecycle_router)
admin_router.include_router(marketplace_review_admin_router)
admin_router.include_router(model_catalog_admin_router)
admin_router.include_router(multi_region_ops_admin_router)
admin_router.include_router(notifications_admin_router)
admin_router.include_router(operations_router)
admin_router.include_router(policies_admin_router)
admin_router.include_router(privacy_compliance_admin_router)
admin_router.include_router(abuse_prevention_admin_router)
admin_router.include_router(security_compliance_admin_router)
admin_router.include_router(settings_router)
admin_router.include_router(tenants_admin_router)
admin_router.include_router(two_person_auth_router)
admin_router.include_router(vault_admin_router)
admin_router.include_router(workspaces_admin_router)
