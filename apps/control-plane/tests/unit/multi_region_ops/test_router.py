from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.multi_region_ops import router as router_module
from platform.multi_region_ops.models import (
    FailoverPlan,
    FailoverPlanRun,
    MaintenanceWindow,
    RegionConfig,
    ReplicationStatus,
)
from platform.multi_region_ops.schemas import (
    CapacityConfidence,
    CapacitySignalResponse,
    FailoverPlanCreateRequest,
    FailoverPlanExecuteRequest,
    FailoverPlanStep,
    FailoverPlanUpdateRequest,
    MaintenanceWindowCreateRequest,
    MaintenanceWindowDisableRequest,
    MaintenanceWindowEnableRequest,
    MaintenanceWindowStatus,
    MaintenanceWindowUpdateRequest,
    RegionConfigCreateRequest,
    RegionConfigUpdateRequest,
    RegionRole,
)
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest


def _now() -> datetime:
    return datetime.now(UTC)


def _region(code: str, role: str = "secondary", *, enabled: bool = True) -> RegionConfig:
    region = RegionConfig(
        region_code=code,
        region_role=role,
        endpoint_urls={"health": f"https://{code}.example/health"},
        rpo_target_minutes=5,
        rto_target_minutes=30,
        enabled=enabled,
    )
    region.id = uuid4()
    region.created_at = _now()
    region.updated_at = region.created_at
    return region


def _replication_status() -> ReplicationStatus:
    row = ReplicationStatus(
        source_region="eu-west",
        target_region="us-east",
        component="postgres",
        lag_seconds=8,
        health="degraded",
        measured_at=_now(),
    )
    row.id = uuid4()
    return row


def _plan() -> FailoverPlan:
    plan = FailoverPlan(
        name="primary-to-dr",
        from_region="eu-west",
        to_region="us-east",
        steps=[{"kind": "custom", "name": "Notify", "parameters": {}}],
        runbook_url="https://runbook.example/failover",
        version=3,
        created_at=_now(),
        updated_at=_now(),
    )
    plan.id = uuid4()
    plan.tested_at = None
    plan.last_executed_at = None
    plan.created_by = None
    return plan


def _run(plan_id: UUID, *, outcome: str = "succeeded") -> FailoverPlanRun:
    run = FailoverPlanRun(
        plan_id=plan_id,
        run_kind="rehearsal",
        outcome=outcome,
        step_outcomes=[
            {
                "step_index": 0,
                "kind": "custom",
                "name": "Notify",
                "outcome": outcome,
                "duration_ms": 4,
                "error_detail": None,
            }
        ],
        initiated_by=None,
        reason="exercise",
        lock_token="token",
        started_at=_now(),
    )
    run.id = uuid4()
    run.ended_at = _now()
    return run


def _window(status: str = "scheduled") -> MaintenanceWindow:
    starts_at = _now() + timedelta(minutes=10)
    window = MaintenanceWindow(
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=45),
        reason="database failover",
        blocks_writes=True,
        announcement_text="Writes are paused",
        status=status,
        created_at=_now(),
        updated_at=_now(),
    )
    window.id = uuid4()
    window.scheduled_by = None
    window.enabled_at = _now() if status == "active" else None
    window.disabled_at = None
    window.disable_failure_reason = None
    return window


class FakeRegionService:
    def __init__(self) -> None:
        self.primary = _region("eu-west", "primary")
        self.secondary = _region("us-east")
        self.deleted: list[UUID] = []
        self.actor_ids: list[UUID | None] = []

    async def list(self, *, enabled_only: bool = False) -> list[RegionConfig]:
        regions = [self.primary, self.secondary]
        return [region for region in regions if region.enabled] if enabled_only else regions

    async def get(self, region_id: UUID) -> RegionConfig:
        assert region_id == self.primary.id
        return self.primary

    async def create(
        self, payload: RegionConfigCreateRequest, *, by_user_id: UUID | None = None
    ) -> RegionConfig:
        self.actor_ids.append(by_user_id)
        return _region(payload.region_code, payload.region_role.value, enabled=payload.enabled)

    async def update(
        self, region_id: UUID, payload: RegionConfigUpdateRequest, *, by_user_id: UUID | None = None
    ) -> RegionConfig:
        self.actor_ids.append(by_user_id)
        region = _region(payload.region_code or "updated", "secondary")
        region.id = region_id
        return region

    async def enable(self, region_id: UUID, *, by_user_id: UUID | None = None) -> RegionConfig:
        self.actor_ids.append(by_user_id)
        region = _region("us-east", enabled=True)
        region.id = region_id
        return region

    async def disable(self, region_id: UUID, *, by_user_id: UUID | None = None) -> RegionConfig:
        self.actor_ids.append(by_user_id)
        region = _region("us-east", enabled=False)
        region.id = region_id
        return region

    async def delete(self, region_id: UUID, *, by_user_id: UUID | None = None) -> None:
        self.actor_ids.append(by_user_id)
        self.deleted.append(region_id)


class FakeProbeRegistry:
    def components(self) -> list[str]:
        return ["postgres"]

    def missing_components(self) -> list[str]:
        return ["kafka"]


class FakeReplicationRepository:
    async def list_replication_statuses_overview(self) -> list[ReplicationStatus]:
        return [_replication_status()]

    async def list_replication_statuses_window(self, **kwargs: Any) -> list[ReplicationStatus]:
        assert kwargs["source"] == "eu-west"
        return [_replication_status()]


class FakeReplicationMonitor:
    def __init__(self) -> None:
        self.repository = FakeReplicationRepository()
        self.probe_registry = FakeProbeRegistry()


class FakeFailoverService:
    def __init__(self) -> None:
        self.plan = _plan()
        self.run = _run(self.plan.id)
        self.deleted: list[UUID] = []
        self.actor_ids: list[UUID | None] = []

    def is_stale(self, plan: FailoverPlan) -> bool:
        assert plan is self.plan
        return True

    async def list_plans(
        self, *, from_region: str | None = None, to_region: str | None = None
    ) -> list[FailoverPlan]:
        assert from_region in {None, "eu-west"}
        assert to_region in {None, "us-east"}
        return [self.plan]

    async def get_plan(self, plan_id: UUID) -> FailoverPlan:
        assert plan_id == self.plan.id
        return self.plan

    async def list_runs(self, plan_id: UUID) -> list[FailoverPlanRun]:
        assert plan_id == self.plan.id
        return [self.run]

    async def get_run(self, run_id: UUID) -> FailoverPlanRun:
        assert run_id == self.run.id
        return self.run

    async def create_plan(
        self, payload: FailoverPlanCreateRequest, *, by_user_id: UUID | None = None
    ) -> FailoverPlan:
        self.actor_ids.append(by_user_id)
        self.plan.name = payload.name
        return self.plan

    async def update_plan(
        self, plan_id: UUID, payload: FailoverPlanUpdateRequest, *, by_user_id: UUID | None = None
    ) -> FailoverPlan:
        self.actor_ids.append(by_user_id)
        self.plan.id = plan_id
        self.plan.name = payload.name or self.plan.name
        return self.plan

    async def rehearse(
        self, plan_id: UUID, *, by_user_id: UUID | None = None, reason: str | None = None
    ) -> FailoverPlanRun:
        assert reason is None
        self.actor_ids.append(by_user_id)
        self.run.plan_id = plan_id
        return self.run

    async def execute(
        self, plan_id: UUID, *, by_user_id: UUID | None = None, reason: str | None = None
    ) -> FailoverPlanRun:
        assert reason == "incident"
        self.actor_ids.append(by_user_id)
        self.run.plan_id = plan_id
        self.run.run_kind = "production"
        return self.run

    async def delete_plan(self, plan_id: UUID, *, by_user_id: UUID | None = None) -> None:
        self.actor_ids.append(by_user_id)
        self.deleted.append(plan_id)


class FakeCapacityService:
    async def get_capacity_overview(
        self, *, workspace_id: UUID | None = None
    ) -> list[CapacitySignalResponse]:
        assert workspace_id is not None
        return [
            CapacitySignalResponse(
                resource_class="compute",
                projection={"source": "test"},
                confidence=CapacityConfidence.ok,
            )
        ]

    async def active_recommendations(
        self, *, workspace_id: UUID | None = None
    ) -> list[CapacitySignalResponse]:
        assert workspace_id is not None
        return await self.get_capacity_overview(workspace_id=workspace_id)


class FakeMaintenanceService:
    def __init__(self, *, active: MaintenanceWindow | None = None) -> None:
        self.window = active or _window()
        self.deleted: list[UUID] = []
        self.actor_ids: list[UUID | None] = []

    async def list_windows(self, **kwargs: Any) -> list[MaintenanceWindow]:
        assert set(kwargs) <= {"status", "since", "until"}
        return [self.window]

    async def get_active_window(self) -> MaintenanceWindow | None:
        return self.window if self.window.status == "active" else None

    def status_banner(self, window: MaintenanceWindow | None) -> dict[str, Any] | None:
        if window is None:
            return None
        return {"window_id": str(window.id), "message": "maintenance"}

    async def schedule(
        self, payload: MaintenanceWindowCreateRequest, *, by_user_id: UUID | None = None
    ) -> MaintenanceWindow:
        self.actor_ids.append(by_user_id)
        self.window.starts_at = payload.starts_at
        self.window.ends_at = payload.ends_at
        return self.window

    async def update(
        self,
        window_id: UUID,
        payload: MaintenanceWindowUpdateRequest,
        *,
        by_user_id: UUID | None = None,
    ) -> MaintenanceWindow:
        self.actor_ids.append(by_user_id)
        self.window.id = window_id
        if payload.reason is not None:
            self.window.reason = payload.reason
        return self.window

    async def enable(self, window_id: UUID, *, by_user_id: UUID | None = None) -> MaintenanceWindow:
        self.actor_ids.append(by_user_id)
        self.window.id = window_id
        self.window.status = "active"
        return self.window

    async def disable(
        self,
        window_id: UUID,
        *,
        by_user_id: UUID | None = None,
        disable_kind: str = "manual",
    ) -> MaintenanceWindow:
        assert disable_kind == "failed"
        self.actor_ids.append(by_user_id)
        self.window.id = window_id
        self.window.status = "completed"
        return self.window

    async def cancel(self, window_id: UUID, *, by_user_id: UUID | None = None) -> MaintenanceWindow:
        self.actor_ids.append(by_user_id)
        self.window.id = window_id
        self.window.status = "cancelled"
        return self.window


@pytest.mark.asyncio
async def test_router_read_and_admin_flows_map_services_to_responses() -> None:
    actor_id = uuid4()
    operator = {"roles": ["operator"], "sub": str(actor_id)}
    superadmin = {"roles": [{"role": "superadmin"}], "sub": str(actor_id)}
    region_service = FakeRegionService()
    monitor = FakeReplicationMonitor()
    failover_service = FakeFailoverService()
    capacity_service = FakeCapacityService()
    maintenance_service = FakeMaintenanceService(active=_window("active"))
    workspace_id = uuid4()

    assert router_module._role_names({"roles": [{"role": "admin"}, "operator", object()]}) == {
        "admin",
        "operator",
    }
    router_module.require_operator(operator)
    router_module.require_superadmin(superadmin)
    with pytest.raises(AuthorizationError):
        router_module.require_operator({"roles": []})
    with pytest.raises(AuthorizationError):
        router_module.require_superadmin(operator)

    regions = await router_module.list_regions(
        enabled_only=True,
        current_user=operator,
        service=region_service,  # type: ignore[arg-type]
    )
    region = await router_module.get_region(
        region_service.primary.id,
        current_user=operator,
        service=region_service,  # type: ignore[arg-type]
    )
    replication = await router_module.get_replication_status(
        current_user=operator,
        service=region_service,  # type: ignore[arg-type]
        monitor=monitor,  # type: ignore[arg-type]
    )
    history = await router_module.get_replication_history(
        source="eu-west",
        target="us-east",
        component="postgres",
        since=None,
        until=None,
        current_user=operator,
        monitor=monitor,  # type: ignore[arg-type]
    )
    plans = await router_module.list_failover_plans(
        from_region="eu-west",
        to_region="us-east",
        current_user=operator,
        service=failover_service,  # type: ignore[arg-type]
    )
    plan = await router_module.get_failover_plan(
        failover_service.plan.id,
        current_user=operator,
        service=failover_service,  # type: ignore[arg-type]
    )
    runs = await router_module.list_failover_runs(
        failover_service.plan.id,
        current_user=operator,
        service=failover_service,  # type: ignore[arg-type]
    )
    run = await router_module.get_failover_run(
        failover_service.run.id,
        current_user=operator,
        service=failover_service,  # type: ignore[arg-type]
    )
    capacity = await router_module.get_capacity_overview(
        workspace_id=workspace_id,
        current_user=operator,
        service=capacity_service,  # type: ignore[arg-type]
    )
    recommendations = await router_module.get_capacity_recommendations(
        workspace_id=workspace_id,
        current_user=operator,
        service=capacity_service,  # type: ignore[arg-type]
    )

    assert regions[0].region_code == "eu-west"
    assert region.id == region_service.primary.id
    assert len(replication.items) == 2
    assert any(item.missing_probe for item in replication.items)
    assert history[0].component.value == "postgres"
    assert plans[0].is_stale is True
    assert plan.is_stale is True
    assert runs[0].id == failover_service.run.id
    assert run.outcome.value == "succeeded"
    assert capacity[0].resource_class == "compute"
    assert recommendations[0].confidence.value == "ok"

    controller = SimpleNamespace(
        get_version_manifest=lambda: {
            "versions": [
                {
                    "runtime_id": "reasoning-engine",
                    "version": "1.25.0",
                    "status": "active",
                }
            ]
        }
    )

    async def get_version_manifest() -> dict[str, Any]:
        return controller.get_version_manifest()

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                clients={
                    "runtime_controller": SimpleNamespace(
                        get_version_manifest=get_version_manifest
                    )
                }
            )
        )
    )
    upgrade = await router_module.get_upgrade_status(request, current_user=operator)  # type: ignore[arg-type]
    assert upgrade.runtime_versions[0].runtime_id == "reasoning-engine"

    created_region = await router_module.create_region(
        RegionConfigCreateRequest(region_code="ap-south", region_role=RegionRole.secondary),
        current_user=superadmin,
        service=region_service,  # type: ignore[arg-type]
    )
    updated_region = await router_module.update_region(
        created_region.id,
        RegionConfigUpdateRequest(region_code="ap-south-1"),
        current_user=superadmin,
        service=region_service,  # type: ignore[arg-type]
    )
    enabled_region = await router_module.enable_region(
        created_region.id,
        current_user=superadmin,
        service=region_service,  # type: ignore[arg-type]
    )
    disabled_region = await router_module.disable_region(
        created_region.id,
        current_user=superadmin,
        service=region_service,  # type: ignore[arg-type]
    )
    delete_response = await router_module.delete_region(
        created_region.id,
        current_user=superadmin,
        service=region_service,  # type: ignore[arg-type]
    )
    threshold_response = await router_module.configure_capacity_thresholds(
        {"compute": 0.8},
        current_user=superadmin,
    )

    assert updated_region.region_code == "ap-south-1"
    assert enabled_region.enabled is True
    assert disabled_region.enabled is False
    assert delete_response.status_code == 204
    assert threshold_response["thresholds"] == {"compute": 0.8}
    assert actor_id in region_service.actor_ids

    create_plan_payload = FailoverPlanCreateRequest(
        name="new-plan",
        from_region="eu-west",
        to_region="us-east",
        steps=[FailoverPlanStep(kind="custom", name="Notify")],
    )
    created_plan = await router_module.create_failover_plan(
        create_plan_payload,
        current_user=superadmin,
        service=failover_service,  # type: ignore[arg-type]
    )
    updated_plan = await router_module.update_failover_plan(
        created_plan.id,
        FailoverPlanUpdateRequest(expected_version=3, name="updated-plan"),
        current_user=superadmin,
        service=failover_service,  # type: ignore[arg-type]
    )
    rehearsed = await router_module.rehearse_failover_plan(
        created_plan.id,
        payload=None,
        current_user=superadmin,
        service=failover_service,  # type: ignore[arg-type]
    )
    executed = await router_module.execute_failover_plan(
        created_plan.id,
        payload=FailoverPlanExecuteRequest(reason="incident"),
        current_user=superadmin,
        service=failover_service,  # type: ignore[arg-type]
    )
    delete_plan_response = await router_module.delete_failover_plan(
        created_plan.id,
        current_user=superadmin,
        service=failover_service,  # type: ignore[arg-type]
    )

    assert created_plan.name == "new-plan"
    assert updated_plan.name == "updated-plan"
    assert rehearsed.run_kind.value == "rehearsal"
    assert executed.run_kind.value == "production"
    assert delete_plan_response.status_code == 204
    assert actor_id in failover_service.actor_ids

    listed_windows = await router_module.list_windows(
        status_filter=MaintenanceWindowStatus.active,
        since=None,
        until=None,
        current_user=operator,
        service=maintenance_service,  # type: ignore[arg-type]
    )
    active_window = await router_module.get_active_window(
        current_user=operator,
        service=maintenance_service,  # type: ignore[arg-type]
    )
    banner = await router_module.get_status_banner(service=maintenance_service)  # type: ignore[arg-type]
    fetched_window = await router_module.get_window(
        maintenance_service.window.id,
        current_user=operator,
        service=maintenance_service,  # type: ignore[arg-type]
    )

    assert listed_windows[0].status.value == "active"
    assert active_window is not None
    assert banner == {"window_id": str(maintenance_service.window.id), "message": "maintenance"}
    assert fetched_window.id == maintenance_service.window.id

    with pytest.raises(ValidationError):
        await router_module.get_window(
            uuid4(),
            current_user=operator,
            service=maintenance_service,  # type: ignore[arg-type]
        )

    starts_at = _now() + timedelta(hours=1)
    scheduled_window = await router_module.schedule_window(
        MaintenanceWindowCreateRequest(
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
        ),
        current_user=superadmin,
        service=maintenance_service,  # type: ignore[arg-type]
    )
    updated_window = await router_module.update_window(
        scheduled_window.id,
        MaintenanceWindowUpdateRequest(reason="updated"),
        current_user=superadmin,
        service=maintenance_service,  # type: ignore[arg-type]
    )
    enabled_window = await router_module.enable_window(
        scheduled_window.id,
        payload=MaintenanceWindowEnableRequest(reason="operator action"),
        current_user=superadmin,
        service=maintenance_service,  # type: ignore[arg-type]
    )
    disabled_window = await router_module.disable_window(
        scheduled_window.id,
        payload=MaintenanceWindowDisableRequest(disable_kind="failed"),
        current_user=superadmin,
        service=maintenance_service,  # type: ignore[arg-type]
    )
    cancelled_window = await router_module.cancel_window(
        scheduled_window.id,
        current_user=superadmin,
        service=maintenance_service,  # type: ignore[arg-type]
    )

    assert updated_window.reason == "updated"
    assert enabled_window.status.value == "active"
    assert disabled_window.status.value == "completed"
    assert cancelled_window.status.value == "cancelled"
    assert actor_id in maintenance_service.actor_ids
