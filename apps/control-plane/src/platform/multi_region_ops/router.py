from __future__ import annotations

from datetime import datetime
from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.multi_region_ops.dependencies import (
    get_capacity_service,
    get_failover_service,
    get_maintenance_mode_service,
    get_region_service,
    get_replication_monitor,
)
from platform.multi_region_ops.models import FailoverPlan
from platform.multi_region_ops.schemas import (
    CapacitySignalResponse,
    FailoverPlanCreateRequest,
    FailoverPlanExecuteRequest,
    FailoverPlanResponse,
    FailoverPlanRunResponse,
    FailoverPlanUpdateRequest,
    MaintenanceWindowCreateRequest,
    MaintenanceWindowDisableRequest,
    MaintenanceWindowEnableRequest,
    MaintenanceWindowResponse,
    MaintenanceWindowStatus,
    MaintenanceWindowUpdateRequest,
    RegionConfigCreateRequest,
    RegionConfigResponse,
    RegionConfigUpdateRequest,
    ReplicationComponent,
    ReplicationHealth,
    ReplicationOverviewResponse,
    ReplicationStatusResponse,
    UpgradeRuntimeVersion,
    UpgradeStatusResponse,
)
from platform.multi_region_ops.services.capacity_service import CapacityService
from platform.multi_region_ops.services.failover_service import FailoverService
from platform.multi_region_ops.services.maintenance_mode_service import MaintenanceModeService
from platform.multi_region_ops.services.region_service import RegionService
from platform.multi_region_ops.services.replication_monitor import ReplicationMonitor
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

router = APIRouter()
regions_router = APIRouter(prefix="/api/v1/regions", tags=["multi-region-ops-regions"])
admin_regions_router = APIRouter(
    prefix="/api/v1/admin/regions",
    tags=["multi-region-ops-admin-regions"],
)
maintenance_router = APIRouter(
    prefix="/api/v1/maintenance",
    tags=["multi-region-ops-maintenance"],
)
admin_maintenance_router = APIRouter(
    prefix="/api/v1/admin/maintenance",
    tags=["multi-region-ops-admin-maintenance"],
)


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    values: set[str] = set()
    if isinstance(roles, list):
        for role in roles:
            if isinstance(role, dict) and role.get("role") is not None:
                values.add(str(role["role"]))
            elif isinstance(role, str):
                values.add(role)
    return values


def _actor_id(current_user: dict[str, Any]) -> UUID | None:
    sub = current_user.get("sub")
    return UUID(str(sub)) if sub is not None else None


def require_operator(current_user: dict[str, Any]) -> None:
    accepted = {"owner", "admin", "operator", "platform_operator", "platform_admin", "superadmin"}
    if _role_names(current_user) & accepted:
        return
    raise AuthorizationError("PERMISSION_DENIED", "Insufficient role for multi-region endpoint")


def require_superadmin(current_user: dict[str, Any]) -> None:
    if _role_names(current_user) & {"superadmin"}:
        return
    raise AuthorizationError("PERMISSION_DENIED", "Superadmin role required")


@regions_router.get("", response_model=list[RegionConfigResponse])
async def list_regions(
    enabled_only: bool = Query(default=False),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: RegionService = Depends(get_region_service),
) -> list[RegionConfigResponse]:
    require_operator(current_user)
    return [
        RegionConfigResponse.model_validate(row)
        for row in await service.list(enabled_only=enabled_only)
    ]


@regions_router.get("/replication-status", response_model=ReplicationOverviewResponse)
async def get_replication_status(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: RegionService = Depends(get_region_service),
    monitor: ReplicationMonitor = Depends(get_replication_monitor),
) -> ReplicationOverviewResponse:
    require_operator(current_user)
    rows = await monitor.repository.list_replication_statuses_overview()
    regions = await service.list(enabled_only=True)
    thresholds = {region.region_code: region.rpo_target_minutes * 60 for region in regions}
    items = [
        ReplicationStatusResponse.model_validate(row).model_copy(
            update={"threshold_seconds": thresholds.get(row.target_region)}
        )
        for row in rows
    ]
    existing = {(item.source_region, item.target_region, item.component.value) for item in items}
    primary = next((region for region in regions if region.region_role == "primary"), None)
    secondaries = [region for region in regions if region.region_role == "secondary"]
    if primary is not None:
        for target in secondaries:
            for component in (
                monitor.probe_registry.components() + monitor.probe_registry.missing_components()
            ):
                key = (primary.region_code, target.region_code, component)
                if key not in existing:
                    items.append(
                        ReplicationStatusResponse(
                            source_region=primary.region_code,
                            target_region=target.region_code,
                            component=ReplicationComponent(component),
                            lag_seconds=None,
                            health=ReplicationHealth.unhealthy,
                            error_detail="replication status missing",
                            threshold_seconds=target.rpo_target_minutes * 60,
                            missing_probe=True,
                        )
                    )
    return ReplicationOverviewResponse(items=items)


@regions_router.get("/replication-status/history", response_model=list[ReplicationStatusResponse])
async def get_replication_history(
    source: str | None = Query(default=None),
    target: str | None = Query(default=None),
    component: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    monitor: ReplicationMonitor = Depends(get_replication_monitor),
) -> list[ReplicationStatusResponse]:
    require_operator(current_user)
    rows = await monitor.repository.list_replication_statuses_window(
        source=source,
        target=target,
        component=component,
        since=since,
        until=until,
    )
    return [ReplicationStatusResponse.model_validate(row) for row in rows]


@regions_router.get("/failover-plans/runs/{run_id}", response_model=FailoverPlanRunResponse)
async def get_failover_run(
    run_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: FailoverService = Depends(get_failover_service),
) -> FailoverPlanRunResponse:
    require_operator(current_user)
    return FailoverPlanRunResponse.model_validate(await service.get_run(run_id))


@regions_router.get("/failover-plans", response_model=list[FailoverPlanResponse])
async def list_failover_plans(
    from_region: str | None = Query(default=None),
    to_region: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: FailoverService = Depends(get_failover_service),
) -> list[FailoverPlanResponse]:
    require_operator(current_user)
    return [
        _plan_response(service, plan)
        for plan in await service.list_plans(from_region=from_region, to_region=to_region)
    ]


@regions_router.get("/failover-plans/{plan_id}", response_model=FailoverPlanResponse)
async def get_failover_plan(
    plan_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: FailoverService = Depends(get_failover_service),
) -> FailoverPlanResponse:
    require_operator(current_user)
    return _plan_response(service, await service.get_plan(plan_id))


@regions_router.get("/failover-plans/{plan_id}/runs", response_model=list[FailoverPlanRunResponse])
async def list_failover_runs(
    plan_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: FailoverService = Depends(get_failover_service),
) -> list[FailoverPlanRunResponse]:
    require_operator(current_user)
    return [FailoverPlanRunResponse.model_validate(row) for row in await service.list_runs(plan_id)]


@regions_router.get(
    "/capacity", response_model=list[CapacitySignalResponse], tags=["multi-region-ops-capacity"]
)
async def get_capacity_overview(
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: CapacityService = Depends(get_capacity_service),
) -> list[CapacitySignalResponse]:
    require_operator(current_user)
    return await service.get_capacity_overview(workspace_id=workspace_id)


@regions_router.get(
    "/capacity/recommendations",
    response_model=list[CapacitySignalResponse],
    tags=["multi-region-ops-capacity"],
)
async def get_capacity_recommendations(
    workspace_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: CapacityService = Depends(get_capacity_service),
) -> list[CapacitySignalResponse]:
    require_operator(current_user)
    return await service.active_recommendations(workspace_id=workspace_id)


@regions_router.get("/upgrade-status", response_model=UpgradeStatusResponse)
async def get_upgrade_status(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> UpgradeStatusResponse:
    require_operator(current_user)
    runtime_controller = request.app.state.clients.get("runtime_controller")
    manifest: Any = None
    if runtime_controller is not None:
        for method_name in ("get_version_manifest", "list_runtime_versions", "version_manifest"):
            method = getattr(runtime_controller, method_name, None)
            if callable(method):
                manifest = await method()
                break
    versions = []
    if isinstance(manifest, dict):
        raw_versions = manifest.get("runtime_versions") or manifest.get("versions") or []
        if isinstance(raw_versions, list):
            versions = [UpgradeRuntimeVersion.model_validate(item) for item in raw_versions]
    return UpgradeStatusResponse(runtime_versions=versions)


@regions_router.get("/{region_id}", response_model=RegionConfigResponse)
async def get_region(
    region_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: RegionService = Depends(get_region_service),
) -> RegionConfigResponse:
    require_operator(current_user)
    return RegionConfigResponse.model_validate(await service.get(region_id))


@admin_regions_router.post(
    "", response_model=RegionConfigResponse, status_code=status.HTTP_201_CREATED
)
async def create_region(
    payload: RegionConfigCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: RegionService = Depends(get_region_service),
) -> RegionConfigResponse:
    require_superadmin(current_user)
    return RegionConfigResponse.model_validate(
        await service.create(payload, by_user_id=_actor_id(current_user))
    )


@admin_regions_router.patch("/{region_id}", response_model=RegionConfigResponse)
async def update_region(
    region_id: UUID,
    payload: RegionConfigUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: RegionService = Depends(get_region_service),
) -> RegionConfigResponse:
    require_superadmin(current_user)
    return RegionConfigResponse.model_validate(
        await service.update(region_id, payload, by_user_id=_actor_id(current_user))
    )


@admin_regions_router.post("/{region_id}/enable", response_model=RegionConfigResponse)
async def enable_region(
    region_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: RegionService = Depends(get_region_service),
) -> RegionConfigResponse:
    require_superadmin(current_user)
    return RegionConfigResponse.model_validate(
        await service.enable(region_id, by_user_id=_actor_id(current_user))
    )


@admin_regions_router.post("/{region_id}/disable", response_model=RegionConfigResponse)
async def disable_region(
    region_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: RegionService = Depends(get_region_service),
) -> RegionConfigResponse:
    require_superadmin(current_user)
    return RegionConfigResponse.model_validate(
        await service.disable(region_id, by_user_id=_actor_id(current_user))
    )


@admin_regions_router.delete("/{region_id}", status_code=204)
async def delete_region(
    region_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: RegionService = Depends(get_region_service),
) -> Response:
    require_superadmin(current_user)
    await service.delete(region_id, by_user_id=_actor_id(current_user))
    return Response(status_code=204)


@admin_regions_router.post("/failover-plans", response_model=FailoverPlanResponse, status_code=201)
async def create_failover_plan(
    payload: FailoverPlanCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: FailoverService = Depends(get_failover_service),
) -> FailoverPlanResponse:
    require_superadmin(current_user)
    return _plan_response(
        service, await service.create_plan(payload, by_user_id=_actor_id(current_user))
    )


@admin_regions_router.patch("/failover-plans/{plan_id}", response_model=FailoverPlanResponse)
async def update_failover_plan(
    plan_id: UUID,
    payload: FailoverPlanUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: FailoverService = Depends(get_failover_service),
) -> FailoverPlanResponse:
    require_superadmin(current_user)
    return _plan_response(
        service, await service.update_plan(plan_id, payload, by_user_id=_actor_id(current_user))
    )


@admin_regions_router.post(
    "/failover-plans/{plan_id}/rehearse", response_model=FailoverPlanRunResponse
)
async def rehearse_failover_plan(
    plan_id: UUID,
    payload: FailoverPlanExecuteRequest | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: FailoverService = Depends(get_failover_service),
) -> FailoverPlanRunResponse:
    require_superadmin(current_user)
    request = payload or FailoverPlanExecuteRequest()
    return FailoverPlanRunResponse.model_validate(
        await service.rehearse(plan_id, by_user_id=_actor_id(current_user), reason=request.reason)
    )


@admin_regions_router.post(
    "/failover-plans/{plan_id}/execute", response_model=FailoverPlanRunResponse
)
async def execute_failover_plan(
    plan_id: UUID,
    payload: FailoverPlanExecuteRequest | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: FailoverService = Depends(get_failover_service),
) -> FailoverPlanRunResponse:
    require_superadmin(current_user)
    request = payload or FailoverPlanExecuteRequest()
    return FailoverPlanRunResponse.model_validate(
        await service.execute(plan_id, by_user_id=_actor_id(current_user), reason=request.reason)
    )


@admin_regions_router.delete("/failover-plans/{plan_id}", status_code=204)
async def delete_failover_plan(
    plan_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: FailoverService = Depends(get_failover_service),
) -> Response:
    require_superadmin(current_user)
    await service.delete_plan(plan_id, by_user_id=_actor_id(current_user))
    return Response(status_code=204)


@admin_regions_router.post(
    "/capacity/thresholds", response_model=dict[str, Any], tags=["multi-region-ops-capacity"]
)
async def configure_capacity_thresholds(
    payload: dict[str, Any],
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    require_superadmin(current_user)
    return {"status": "accepted", "thresholds": payload}


@maintenance_router.get("/windows", response_model=list[MaintenanceWindowResponse])
async def list_windows(
    status_filter: MaintenanceWindowStatus | None = Query(default=None, alias="status"),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: MaintenanceModeService = Depends(get_maintenance_mode_service),
) -> list[MaintenanceWindowResponse]:
    require_operator(current_user)
    return [
        MaintenanceWindowResponse.model_validate(row)
        for row in await service.list_windows(
            status=status_filter.value if status_filter else None,
            since=since,
            until=until,
        )
    ]


@maintenance_router.get("/windows/active", response_model=MaintenanceWindowResponse | None)
async def get_active_window(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: MaintenanceModeService = Depends(get_maintenance_mode_service),
) -> MaintenanceWindowResponse | None:
    require_operator(current_user)
    window = await service.get_active_window()
    return MaintenanceWindowResponse.model_validate(window) if window is not None else None


@maintenance_router.get("/status-banner", response_model=dict[str, Any] | None)
async def get_status_banner(
    service: MaintenanceModeService = Depends(get_maintenance_mode_service),
) -> dict[str, Any] | None:
    return service.status_banner(await service.get_active_window())


@maintenance_router.get("/windows/{window_id}", response_model=MaintenanceWindowResponse)
async def get_window(
    window_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: MaintenanceModeService = Depends(get_maintenance_mode_service),
) -> MaintenanceWindowResponse:
    require_operator(current_user)
    rows = await service.list_windows()
    match = next((row for row in rows if row.id == window_id), None)
    if match is None:
        raise ValidationError("MAINTENANCE_WINDOW_NOT_FOUND", "Maintenance window not found")
    return MaintenanceWindowResponse.model_validate(match)


@admin_maintenance_router.post(
    "/windows", response_model=MaintenanceWindowResponse, status_code=201
)
async def schedule_window(
    payload: MaintenanceWindowCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: MaintenanceModeService = Depends(get_maintenance_mode_service),
) -> MaintenanceWindowResponse:
    require_superadmin(current_user)
    return MaintenanceWindowResponse.model_validate(
        await service.schedule(payload, by_user_id=_actor_id(current_user))
    )


@admin_maintenance_router.patch("/windows/{window_id}", response_model=MaintenanceWindowResponse)
async def update_window(
    window_id: UUID,
    payload: MaintenanceWindowUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: MaintenanceModeService = Depends(get_maintenance_mode_service),
) -> MaintenanceWindowResponse:
    require_superadmin(current_user)
    return MaintenanceWindowResponse.model_validate(
        await service.update(window_id, payload, by_user_id=_actor_id(current_user))
    )


@admin_maintenance_router.post(
    "/windows/{window_id}/enable", response_model=MaintenanceWindowResponse
)
async def enable_window(
    window_id: UUID,
    payload: MaintenanceWindowEnableRequest | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: MaintenanceModeService = Depends(get_maintenance_mode_service),
) -> MaintenanceWindowResponse:
    del payload
    require_superadmin(current_user)
    return MaintenanceWindowResponse.model_validate(
        await service.enable(window_id, by_user_id=_actor_id(current_user))
    )


@admin_maintenance_router.post(
    "/windows/{window_id}/disable", response_model=MaintenanceWindowResponse
)
async def disable_window(
    window_id: UUID,
    payload: MaintenanceWindowDisableRequest | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: MaintenanceModeService = Depends(get_maintenance_mode_service),
) -> MaintenanceWindowResponse:
    require_superadmin(current_user)
    request = payload or MaintenanceWindowDisableRequest()
    return MaintenanceWindowResponse.model_validate(
        await service.disable(
            window_id,
            by_user_id=_actor_id(current_user),
            disable_kind=request.disable_kind,
        )
    )


@admin_maintenance_router.post(
    "/windows/{window_id}/cancel", response_model=MaintenanceWindowResponse
)
async def cancel_window(
    window_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: MaintenanceModeService = Depends(get_maintenance_mode_service),
) -> MaintenanceWindowResponse:
    require_superadmin(current_user)
    return MaintenanceWindowResponse.model_validate(
        await service.cancel(window_id, by_user_id=_actor_id(current_user))
    )


def _plan_response(service: FailoverService, plan: FailoverPlan) -> FailoverPlanResponse:
    return FailoverPlanResponse.model_validate(plan).model_copy(
        update={"is_stale": service.is_stale(plan)}
    )


router.include_router(regions_router)
router.include_router(admin_regions_router)
router.include_router(maintenance_router)
router.include_router(admin_maintenance_router)
