from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from platform.common.config import PlatformSettings
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.multi_region_ops import dependencies as deps
from platform.multi_region_ops.middleware.maintenance_gate import MaintenanceGateMiddleware
from platform.multi_region_ops.models import (
    FailoverPlan,
    FailoverPlanRun,
    MaintenanceWindow,
    RegionConfig,
)
from platform.multi_region_ops.router import router
from platform.multi_region_ops.schemas import (
    FailoverPlanCreateRequest,
    FailoverPlanStep,
    RegionConfigCreateRequest,
    RegionConfigUpdateRequest,
    RegionRole,
)
from platform.multi_region_ops.services.capacity_service import CapacityService
from platform.multi_region_ops.services.failover_service import FailoverService
from platform.multi_region_ops.services.failover_steps.base import StepOutcome
from platform.multi_region_ops.services.maintenance_mode_service import MaintenanceModeService
from platform.multi_region_ops.services.probes.base import (
    ReplicationMeasurement,
    ReplicationProbeRegistry,
)
from platform.multi_region_ops.services.region_service import RegionService
from platform.multi_region_ops.services.replication_monitor import ReplicationMonitor
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI

REPO_ROOT = Path(__file__).resolve().parents[5]
OPERATOR_USER = {
    "sub": str(uuid4()),
    "roles": [{"role": "platform_operator"}],
}
SUPERADMIN_USER = {
    "sub": str(uuid4()),
    "roles": [{"role": "superadmin"}],
}


def now() -> datetime:
    return datetime.now(UTC)


def make_region(
    code: str,
    role: str = "secondary",
    *,
    enabled: bool = True,
    rpo: int = 15,
    endpoints: dict[str, Any] | None = None,
) -> RegionConfig:
    region = RegionConfig(
        region_code=code,
        region_role=role,
        endpoint_urls=endpoints or {"health": f"https://{code}.example/health"},
        rpo_target_minutes=rpo,
        rto_target_minutes=60,
        enabled=enabled,
    )
    region.id = uuid4()
    region.created_at = now()
    region.updated_at = region.created_at
    return region


def make_window(
    *,
    status: str = "scheduled",
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    reason: str = "database maintenance",
) -> MaintenanceWindow:
    starts = starts_at or now() + timedelta(minutes=15)
    window = MaintenanceWindow(
        starts_at=starts,
        ends_at=ends_at or starts + timedelta(minutes=45),
        reason=reason,
        blocks_writes=True,
        announcement_text="Writes are paused for maintenance",
        status=status,
        created_at=now(),
        updated_at=now(),
    )
    window.id = uuid4()
    window.scheduled_by = None
    window.enabled_at = now() if status == "active" else None
    window.disabled_at = None
    window.disable_failure_reason = None
    return window


def make_plan(
    *,
    steps: list[dict[str, Any]] | None = None,
    tested_at: datetime | None = None,
) -> FailoverPlan:
    plan = FailoverPlan(
        name="primary-to-dr",
        from_region="eu-west",
        to_region="us-east",
        steps=steps or [{"kind": "custom", "name": "Notify", "parameters": {}}],
        runbook_url="/docs/runbooks/failover.md",
        version=1,
        created_at=now(),
        updated_at=now(),
    )
    plan.id = uuid4()
    plan.tested_at = tested_at
    plan.last_executed_at = None
    plan.created_by = None
    return plan


def make_run(plan_id: UUID, *, outcome: str = "in_progress") -> FailoverPlanRun:
    run = FailoverPlanRun(
        plan_id=plan_id,
        run_kind="rehearsal",
        outcome=outcome,
        step_outcomes=[],
        initiated_by=None,
        reason="quarterly exercise",
        lock_token="lock-token",
        started_at=now(),
    )
    run.id = uuid4()
    run.ended_at = None if outcome == "in_progress" else now()
    return run


class RecordingAudit:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.entries: list[tuple[UUID, str, bytes]] = []

    async def append(self, entity_id: UUID, event_source: str, canonical: bytes) -> None:
        if self.fail:
            raise RuntimeError("audit chain unavailable")
        self.entries.append((entity_id, event_source, canonical))


class RecordingProducer:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> None:
        self.events.append(kwargs)


class RecordingIncidentTrigger:
    def __init__(self) -> None:
        self.signals: list[Any] = []

    async def fire(self, signal: Any) -> SimpleNamespace:
        self.signals.append(signal)
        return SimpleNamespace(incident_id=uuid4())


class RecordingIncidentService:
    def __init__(self) -> None:
        self.incident_id = uuid4()
        self.repository = SimpleNamespace(find_open_incident_by_fingerprint=self._find)
        self.resolved: list[UUID] = []

    async def _find(self, fingerprint: str) -> SimpleNamespace:
        return SimpleNamespace(id=self.incident_id, fingerprint=fingerprint)

    async def resolve(self, incident_id: UUID, **kwargs: Any) -> None:
        del kwargs
        self.resolved.append(incident_id)


class FakeRedis:
    def __init__(self, *, fail_delete: bool = False) -> None:
        self.values: dict[str, bytes] = {}
        self.fail_delete = fail_delete

    async def set(self, key: str, value: bytes, *, ttl: int) -> None:
        assert ttl > 0
        self.values[key] = value

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        if self.fail_delete:
            raise RuntimeError("redis unavailable")
        self.values.pop(key, None)


class MultiRegionMemoryRepository:
    def __init__(self) -> None:
        self.regions: dict[UUID, RegionConfig] = {}
        self.replication_rows: list[Any] = []
        self.plans: dict[UUID, FailoverPlan] = {}
        self.runs: dict[UUID, FailoverPlanRun] = {}
        self.windows: dict[UUID, MaintenanceWindow] = {}

    async def insert_region(self, **kwargs: Any) -> RegionConfig:
        region = make_region(
            kwargs["region_code"],
            kwargs["region_role"],
            enabled=kwargs["enabled"],
            rpo=kwargs["rpo_target_minutes"],
            endpoints=kwargs["endpoint_urls"],
        )
        self.regions[region.id] = region
        return region

    async def get_region(self, region_id: UUID) -> RegionConfig | None:
        return self.regions.get(region_id)

    async def get_region_by_code(self, code: str) -> RegionConfig | None:
        return next((row for row in self.regions.values() if row.region_code == code), None)

    async def list_regions(self, *, enabled_only: bool = False) -> list[RegionConfig]:
        rows = sorted(self.regions.values(), key=lambda row: row.region_code)
        return [row for row in rows if row.enabled] if enabled_only else rows

    async def update_region(self, region_id: UUID, **updates: Any) -> RegionConfig | None:
        region = self.regions.get(region_id)
        if region is None:
            return None
        for key, value in updates.items():
            if value is not None:
                setattr(region, key, value)
        region.updated_at = now()
        return region

    async def count_active_primaries(self, *, exclude_region_id: UUID | None = None) -> int:
        return sum(
            1
            for row in self.regions.values()
            if row.region_role == "primary"
            and row.enabled
            and (exclude_region_id is None or row.id != exclude_region_id)
        )

    async def delete_region(self, region_id: UUID) -> bool:
        return self.regions.pop(region_id, None) is not None

    async def has_dependent_plans(self, region_code: str) -> bool:
        return any(
            plan.from_region == region_code or plan.to_region == region_code
            for plan in self.plans.values()
        )

    async def insert_replication_status(self, **kwargs: Any) -> Any:
        row = SimpleNamespace(id=uuid4(), measured_at=kwargs.get("measured_at") or now(), **kwargs)
        self.replication_rows.append(row)
        return row

    async def list_replication_statuses_overview(self) -> list[Any]:
        latest: dict[tuple[str, str, str], Any] = {}
        for row in sorted(self.replication_rows, key=lambda item: item.measured_at):
            latest[(row.source_region, row.target_region, row.component)] = row
        return list(latest.values())

    async def list_replication_statuses_window(self, **kwargs: Any) -> list[Any]:
        source = kwargs.get("source")
        target = kwargs.get("target")
        component = kwargs.get("component")
        return [
            row
            for row in self.replication_rows
            if (source is None or row.source_region == source)
            and (target is None or row.target_region == target)
            and (component is None or row.component == component)
        ]

    async def count_consecutive_over_threshold(
        self,
        *,
        source: str,
        target: str,
        component: str,
        threshold_seconds: int,
        n: int,
    ) -> bool:
        rows = self._latest_replication_rows(source, target, component, n)
        return len(rows) == n and all(
            row.health != "paused"
            and row.lag_seconds is not None
            and row.lag_seconds > threshold_seconds
            for row in rows
        )

    async def count_consecutive_at_or_below_threshold(
        self,
        *,
        source: str,
        target: str,
        component: str,
        threshold_seconds: int,
        n: int,
    ) -> bool:
        rows = self._latest_replication_rows(source, target, component, n)
        return len(rows) == n and all(
            row.health == "healthy"
            and row.lag_seconds is not None
            and row.lag_seconds <= threshold_seconds
            for row in rows
        )

    def _latest_replication_rows(
        self, source: str, target: str, component: str, n: int
    ) -> list[Any]:
        rows = [
            row
            for row in self.replication_rows
            if row.source_region == source
            and row.target_region == target
            and row.component == component
        ]
        return sorted(rows, key=lambda item: item.measured_at, reverse=True)[:n]

    async def insert_plan(self, **kwargs: Any) -> FailoverPlan:
        plan = make_plan(steps=kwargs["steps"])
        plan.name = kwargs["name"]
        plan.from_region = kwargs["from_region"]
        plan.to_region = kwargs["to_region"]
        plan.runbook_url = kwargs["runbook_url"]
        plan.created_by = kwargs["created_by"]
        self.plans[plan.id] = plan
        return plan

    async def get_plan(self, plan_id: UUID) -> FailoverPlan | None:
        return self.plans.get(plan_id)

    async def get_plan_by_name(self, name: str) -> FailoverPlan | None:
        return next((plan for plan in self.plans.values() if plan.name == name), None)

    async def list_plans(
        self, *, from_region: str | None = None, to_region: str | None = None
    ) -> list[FailoverPlan]:
        return [
            plan
            for plan in self.plans.values()
            if (from_region is None or plan.from_region == from_region)
            and (to_region is None or plan.to_region == to_region)
        ]

    async def update_plan(
        self,
        plan_id: UUID,
        *,
        expected_version: int,
        updates: dict[str, Any],
    ) -> FailoverPlan | None:
        plan = self.plans.get(plan_id)
        if plan is None or plan.version != expected_version:
            return None
        for key, value in updates.items():
            if value is not None:
                setattr(plan, key, value)
        plan.version += 1
        plan.updated_at = now()
        return plan

    async def delete_plan(self, plan_id: UUID) -> bool:
        return self.plans.pop(plan_id, None) is not None

    async def has_in_progress_runs(self, plan_id: UUID) -> bool:
        return any(
            run.plan_id == plan_id and run.outcome == "in_progress"
            for run in self.runs.values()
        )

    async def insert_plan_run(self, **kwargs: Any) -> FailoverPlanRun:
        run = make_run(kwargs["plan_id"])
        run.run_kind = kwargs["run_kind"]
        run.initiated_by = kwargs["initiated_by"]
        run.reason = kwargs["reason"]
        run.lock_token = kwargs["lock_token"]
        self.runs[run.id] = run
        return run

    async def update_plan_run_outcome(
        self, run_id: UUID, *, outcome: str, ended_at: datetime | None = None
    ) -> FailoverPlanRun | None:
        run = self.runs.get(run_id)
        if run is None:
            return None
        run.outcome = outcome
        run.ended_at = ended_at
        return run

    async def append_plan_run_step_outcome(
        self, run_id: UUID, step_outcome: dict[str, Any]
    ) -> FailoverPlanRun | None:
        run = self.runs.get(run_id)
        if run is None:
            return None
        run.step_outcomes = [*run.step_outcomes, step_outcome]
        return run

    async def get_plan_run(self, run_id: UUID) -> FailoverPlanRun | None:
        return self.runs.get(run_id)

    async def list_plan_runs(self, plan_id: UUID) -> list[FailoverPlanRun]:
        return [run for run in self.runs.values() if run.plan_id == plan_id]

    async def get_latest_in_progress_run(
        self, *, from_region: str, to_region: str
    ) -> FailoverPlanRun | None:
        for run in self.runs.values():
            plan = self.plans.get(run.plan_id)
            if (
                plan is not None
                and plan.from_region == from_region
                and plan.to_region == to_region
                and run.outcome == "in_progress"
            ):
                return run
        return None

    async def mark_plan_tested(self, plan_id: UUID, ts: datetime) -> None:
        self.plans[plan_id].tested_at = ts

    async def mark_plan_executed(self, plan_id: UUID, ts: datetime) -> None:
        self.plans[plan_id].last_executed_at = ts

    async def insert_window(self, **kwargs: Any) -> MaintenanceWindow:
        window = make_window(
            starts_at=kwargs["starts_at"],
            ends_at=kwargs["ends_at"],
            reason=kwargs["reason"] or "maintenance",
        )
        window.blocks_writes = kwargs["blocks_writes"]
        window.announcement_text = kwargs["announcement_text"]
        window.scheduled_by = kwargs["scheduled_by"]
        self.windows[window.id] = window
        return window

    async def get_window(self, window_id: UUID) -> MaintenanceWindow | None:
        return self.windows.get(window_id)

    async def get_active_window(self) -> MaintenanceWindow | None:
        return next((row for row in self.windows.values() if row.status == "active"), None)

    async def list_windows(
        self,
        *,
        status: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[MaintenanceWindow]:
        return [
            row
            for row in self.windows.values()
            if (status is None or row.status == status)
            and (since is None or row.ends_at >= since)
            and (until is None or row.starts_at <= until)
        ]

    async def update_window_status(
        self, window_id: UUID, *, status: str, **fields: Any
    ) -> MaintenanceWindow | None:
        window = self.windows.get(window_id)
        if window is None:
            return None
        window.status = status
        window.updated_at = now()
        for key, value in fields.items():
            setattr(window, key, value)
        return window

    async def update_window(self, window_id: UUID, **fields: Any) -> MaintenanceWindow | None:
        window = self.windows.get(window_id)
        if window is None:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(window, key, value)
        window.updated_at = now()
        return window

    async def find_overlapping_windows(
        self,
        *,
        starts_at: datetime,
        ends_at: datetime,
        exclude_id: UUID | None = None,
    ) -> list[MaintenanceWindow]:
        return [
            row
            for row in self.windows.values()
            if row.status in {"scheduled", "active"}
            and row.id != exclude_id
            and row.starts_at < ends_at
            and row.ends_at > starts_at
        ]


class RecordingStepAdapter:
    kind = "custom"

    def __init__(self, *, fail_on_call: int | None = None) -> None:
        self.fail_on_call = fail_on_call
        self.calls: list[dict[str, Any]] = []

    async def execute(self, **kwargs: Any) -> StepOutcome:
        self.calls.append(kwargs)
        parameters = kwargs["parameters"]
        call_number = len(self.calls)
        failed = self.fail_on_call == call_number
        return StepOutcome(
            kind=self.kind,
            name=str(parameters["name"]),
            outcome="failed" if failed else "succeeded",
            duration_ms=5,
            error_detail="step failed" if failed else None,
        )


class FixedProbe:
    component = "postgres"

    def __init__(
        self,
        *,
        lag_seconds: int | None = 0,
        health: str = "healthy",
        pause_reason: str | None = None,
    ) -> None:
        self.lag_seconds = lag_seconds
        self.health = health
        self.pause_reason = pause_reason

    async def measure(
        self, *, source: RegionConfig, target: RegionConfig
    ) -> ReplicationMeasurement:
        del source, target
        return ReplicationMeasurement(
            component=self.component,
            lag_seconds=self.lag_seconds,
            health=self.health,
            pause_reason=self.pause_reason,
        )


class FakeForecastService:
    def __init__(self, *, insufficient_history: bool = False) -> None:
        self.insufficient_history = insufficient_history

    async def get_latest_forecast(self, workspace_id: UUID) -> Any:
        return SimpleNamespace(
            workspace_id=workspace_id,
            forecast_cents=Decimal("1200.00"),
            confidence_interval={
                "status": "insufficient_history" if self.insufficient_history else "ok",
                "points": 2 if self.insufficient_history else 12,
            },
        )


class FakeAnalyticsService:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or [
            {"resource_class": "compute", "utilization": 0.62},
            {"resource_class": "storage", "utilization": 0.71},
        ]

    async def get_workspace_usage_rollups(self, workspace_id: UUID) -> list[dict[str, Any]]:
        del workspace_id
        return self.rows


def seeded_repository() -> MultiRegionMemoryRepository:
    repository = MultiRegionMemoryRepository()
    primary = make_region("eu-west", "primary", rpo=1)
    secondary = make_region("us-east", "secondary", rpo=1)
    repository.regions[primary.id] = primary
    repository.regions[secondary.id] = secondary
    return repository


def create_failover_plan_request(step_count: int = 5) -> FailoverPlanCreateRequest:
    return FailoverPlanCreateRequest(
        name=f"primary-to-dr-{uuid4().hex[:6]}",
        from_region="eu-west",
        to_region="us-east",
        steps=[
            FailoverPlanStep(kind="custom", name=f"Step {index + 1}")
            for index in range(step_count)
        ],
        runbook_url="/docs/runbooks/failover.md",
    )


def build_monitor(
    repository: MultiRegionMemoryRepository,
    *,
    settings: PlatformSettings | None = None,
    probe: FixedProbe | None = None,
    trigger: RecordingIncidentTrigger | None = None,
    incident_service: RecordingIncidentService | None = None,
) -> tuple[ReplicationMonitor, RecordingIncidentTrigger]:
    registry = ReplicationProbeRegistry()
    registry.register(probe or FixedProbe())
    incident_trigger = trigger or RecordingIncidentTrigger()
    monitor = ReplicationMonitor(
        repository=repository,  # type: ignore[arg-type]
        settings=settings or PlatformSettings(feature_multi_region=True),
        probe_registry=registry,
        incident_trigger=incident_trigger,  # type: ignore[arg-type]
        incident_service=incident_service,  # type: ignore[arg-type]
    )
    return monitor, incident_trigger


def build_services(
    repository: MultiRegionMemoryRepository,
    *,
    settings: PlatformSettings | None = None,
    audit: RecordingAudit | None = None,
    redis: FakeRedis | None = None,
    producer: RecordingProducer | None = None,
    incident_trigger: RecordingIncidentTrigger | None = None,
    step_adapter: RecordingStepAdapter | None = None,
    insufficient_history: bool = False,
) -> dict[str, Any]:
    resolved_settings = settings or PlatformSettings(
        feature_multi_region=True,
        feature_maintenance_mode=True,
    )
    audit_service = audit or RecordingAudit()
    incident = incident_trigger or RecordingIncidentTrigger()
    event_producer = producer or RecordingProducer()
    region_service = RegionService(
        repository=repository,  # type: ignore[arg-type]
        audit_chain_service=audit_service,  # type: ignore[arg-type]
    )
    monitor, _ = build_monitor(repository, settings=resolved_settings, trigger=incident)
    failover_service = FailoverService(
        repository=repository,  # type: ignore[arg-type]
        settings=resolved_settings,
        redis_client=None,
        producer=event_producer,  # type: ignore[arg-type]
        audit_chain_service=audit_service,  # type: ignore[arg-type]
        step_adapters={"custom": step_adapter or RecordingStepAdapter()},  # type: ignore[arg-type]
    )
    maintenance_service = MaintenanceModeService(
        repository=repository,  # type: ignore[arg-type]
        settings=resolved_settings,
        redis_client=redis,  # type: ignore[arg-type]
        producer=event_producer,  # type: ignore[arg-type]
        incident_trigger=incident,  # type: ignore[arg-type]
        audit_chain_service=audit_service,  # type: ignore[arg-type]
    )
    capacity_service = CapacityService(
        settings=resolved_settings,
        cost_governance_service=SimpleNamespace(
            forecast_service=FakeForecastService(insufficient_history=insufficient_history)
        ),
        analytics_service=FakeAnalyticsService([] if insufficient_history else None),
        incident_trigger=incident,  # type: ignore[arg-type]
    )
    return {
        "settings": resolved_settings,
        "audit": audit_service,
        "producer": event_producer,
        "incident_trigger": incident,
        "region": region_service,
        "monitor": monitor,
        "failover": failover_service,
        "maintenance": maintenance_service,
        "capacity": capacity_service,
    }


def build_app(
    services: dict[str, Any],
    *,
    current_user: dict[str, Any] | None = None,
    runtime_manifest: dict[str, Any] | None = None,
) -> FastAPI:
    app = FastAPI()
    app.state.settings = services["settings"]
    app.state.clients = {
        "runtime_controller": SimpleNamespace(
            get_version_manifest=lambda: asyncio.sleep(0, result=runtime_manifest or {})
        )
    }
    app.add_exception_handler(PlatformError, platform_exception_handler)
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: current_user or SUPERADMIN_USER
    app.dependency_overrides[deps.get_region_service] = lambda: services["region"]
    app.dependency_overrides[deps.get_replication_monitor] = lambda: services["monitor"]
    app.dependency_overrides[deps.get_failover_service] = lambda: services["failover"]
    app.dependency_overrides[deps.get_maintenance_mode_service] = lambda: services["maintenance"]
    app.dependency_overrides[deps.get_capacity_service] = lambda: services["capacity"]
    return app


def build_gate_app(
    *,
    settings: PlatformSettings,
    redis: FakeRedis | None = None,
) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.state.clients = {"redis": redis} if redis is not None else {}
    app.add_middleware(MaintenanceGateMiddleware)

    @app.get("/api/v1/regions/replication-status")
    async def read_region_status() -> dict[str, str]:
        return {"status": "ok"}

    @app.head("/api/v1/regions/replication-status")
    async def head_region_status() -> None:
        return None

    @app.options("/api/v1/regions/replication-status")
    async def options_region_status() -> dict[str, list[str]]:
        return {"allow": ["GET", "HEAD", "OPTIONS"]}

    @app.post("/api/v1/admin/regions")
    async def create_region_endpoint() -> dict[str, str]:
        return {"status": "created"}

    @app.put("/api/v1/admin/regions/region-1")
    async def replace_region_endpoint() -> dict[str, str]:
        return {"status": "updated"}

    @app.patch("/api/v1/admin/regions/region-1")
    async def patch_region_endpoint() -> dict[str, str]:
        return {"status": "patched"}

    @app.delete("/api/v1/admin/regions/region-1")
    async def delete_region_endpoint() -> dict[str, str]:
        return {"status": "deleted"}

    return app


async def async_client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


def superadmin_create_payload(code: str, role: RegionRole) -> RegionConfigCreateRequest:
    return RegionConfigCreateRequest(
        region_code=code,
        region_role=role,
        endpoint_urls={"postgres_replica_dsn_ref": "secret/data/multi-region/postgres"},
    )


async def create_primary_and_secondary(repository: MultiRegionMemoryRepository) -> None:
    service = RegionService(repository=repository)  # type: ignore[arg-type]
    await service.create(superadmin_create_payload("eu-west", RegionRole.primary))
    await service.create(superadmin_create_payload("us-east", RegionRole.secondary))


async def promote_secondary(service: RegionService, region_id: UUID) -> None:
    await service.update(region_id, RegionConfigUpdateRequest(region_role=RegionRole.primary))
