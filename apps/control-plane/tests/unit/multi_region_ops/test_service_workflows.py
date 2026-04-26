from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.multi_region_ops import dependencies as multi_region_dependencies
from platform.multi_region_ops.constants import REDIS_KEY_ACTIVE_WINDOW, REPLICATION_COMPONENTS
from platform.multi_region_ops.exceptions import (
    ActiveActiveConfigurationRefusedError,
    FailoverInProgressError,
    FailoverPlanNotFoundError,
    FailoverRunNotFoundError,
    MaintenanceDisableFailedError,
    MaintenanceWindowInPastError,
    MaintenanceWindowNotFoundError,
    MaintenanceWindowOverlapError,
    RegionNotFoundError,
)
from platform.multi_region_ops.middleware import maintenance_gate as maintenance_gate_module
from platform.multi_region_ops.middleware.maintenance_gate import (
    MaintenanceGateMiddleware,
)
from platform.multi_region_ops.middleware.maintenance_gate import (
    _aware as middleware_aware,
)
from platform.multi_region_ops.models import (
    FailoverPlan,
    FailoverPlanRun,
    MaintenanceWindow,
    RegionConfig,
)
from platform.multi_region_ops.schemas import (
    FailoverPlanCreateRequest,
    FailoverPlanStep,
    FailoverPlanUpdateRequest,
    MaintenanceWindowCreateRequest,
    MaintenanceWindowUpdateRequest,
    RegionConfigCreateRequest,
    RegionConfigUpdateRequest,
    RegionRole,
)
from platform.multi_region_ops.service import MultiRegionOpsService
from platform.multi_region_ops.services import capacity_service as capacity_module
from platform.multi_region_ops.services.failover_service import FailoverService
from platform.multi_region_ops.services.failover_steps import verify_health as verify_health_module
from platform.multi_region_ops.services.failover_steps.base import NoopStepAdapter, StepOutcome
from platform.multi_region_ops.services.failover_steps.verify_health import VerifyHealthStepAdapter
from platform.multi_region_ops.services.maintenance_mode_service import (
    MaintenanceModeService,
    _window_from_cache,
)
from platform.multi_region_ops.services.maintenance_mode_service import (
    _aware as maintenance_aware,
)
from platform.multi_region_ops.services.probes import opensearch as opensearch_module
from platform.multi_region_ops.services.probes import qdrant as qdrant_module
from platform.multi_region_ops.services.probes.base import (
    ReplicationMeasurement,
    ReplicationProbeRegistry,
)
from platform.multi_region_ops.services.probes.clickhouse import ClickHouseReplicationProbe, _as_int
from platform.multi_region_ops.services.probes.kafka import KafkaReplicationProbe
from platform.multi_region_ops.services.probes.kafka import _extract_lag as _extract_kafka_lag
from platform.multi_region_ops.services.probes.neo4j import Neo4jReplicationProbe, _extract_tx_lag
from platform.multi_region_ops.services.probes.opensearch import (
    OpenSearchReplicationProbe,
    _extract_shard_lag,
)
from platform.multi_region_ops.services.probes.postgres import (
    PostgresReplicationProbe,
    _interval_to_seconds,
)
from platform.multi_region_ops.services.probes.qdrant import QdrantReplicationProbe
from platform.multi_region_ops.services.probes.qdrant import _extract_lag as _extract_qdrant_lag
from platform.multi_region_ops.services.probes.s3 import (
    S3ReplicationProbe,
    _extract_s3_lag,
    _secret_or_value,
)
from platform.multi_region_ops.services.region_service import RegionService
from platform.multi_region_ops.services.replication_monitor import (
    ReplicationMonitor,
    replication_fingerprint,
)
from types import ModuleType, SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError


def _now() -> datetime:
    return datetime.now(UTC)


def _region(
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
        endpoint_urls=endpoints or {},
        rpo_target_minutes=rpo,
        rto_target_minutes=60,
        enabled=enabled,
    )
    region.id = uuid4()
    region.created_at = _now()
    region.updated_at = region.created_at
    return region


def _window(
    *,
    status: str = "scheduled",
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    reason: str = "maintenance",
) -> MaintenanceWindow:
    starts = starts_at or _now() + timedelta(minutes=10)
    ends = ends_at or starts + timedelta(minutes=30)
    window = MaintenanceWindow(
        starts_at=starts,
        ends_at=ends,
        reason=reason,
        blocks_writes=True,
        announcement_text="Writes are paused",
        status=status,
        created_at=_now(),
        updated_at=_now(),
    )
    window.id = uuid4()
    return window


def _plan(*, steps: list[dict[str, Any]] | None = None) -> FailoverPlan:
    plan = FailoverPlan(
        name="primary-to-dr",
        from_region="eu-west",
        to_region="us-east",
        steps=steps or [{"kind": "custom", "name": "Notify", "parameters": {}}],
        runbook_url=None,
        version=1,
        created_at=_now(),
        updated_at=_now(),
    )
    plan.id = uuid4()
    plan.tested_at = None
    plan.last_executed_at = None
    plan.created_by = None
    return plan


def _run(plan_id: UUID, *, outcome: str = "in_progress") -> FailoverPlanRun:
    run = FailoverPlanRun(
        plan_id=plan_id,
        run_kind="rehearsal",
        outcome=outcome,
        step_outcomes=[],
        reason="exercise",
        lock_token="token",
        started_at=_now(),
    )
    run.id = uuid4()
    run.ended_at = None
    run.initiated_by = None
    return run


class FakeAudit:
    def __init__(self) -> None:
        self.entries: list[tuple[UUID, str, bytes]] = []

    async def append(self, entity_id: UUID, event_source: str, canonical: bytes) -> None:
        self.entries.append((entity_id, event_source, canonical))


class FakeProducer:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, **kwargs: Any) -> None:
        self.events.append(kwargs)


class FakeIncidentTrigger:
    def __init__(self) -> None:
        self.signals: list[Any] = []

    async def fire(self, signal: Any) -> SimpleNamespace:
        self.signals.append(signal)
        return SimpleNamespace(incident_id=uuid4())


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


class FakeRegionRepository:
    def __init__(self) -> None:
        self.regions: dict[UUID, RegionConfig] = {}
        self.dependent_region_codes: set[str] = set()

    async def insert_region(self, **kwargs: Any) -> RegionConfig:
        region = _region(
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
        return next(
            (region for region in self.regions.values() if region.region_code == code),
            None,
        )

    async def update_region(self, region_id: UUID, **updates: Any) -> RegionConfig | None:
        region = self.regions.get(region_id)
        if region is None:
            return None
        for key, value in updates.items():
            if value is not None:
                setattr(region, key, value)
        return region

    async def count_active_primaries(self, *, exclude_region_id: UUID | None = None) -> int:
        return sum(
            1
            for region in self.regions.values()
            if region.region_role == "primary"
            and region.enabled
            and (exclude_region_id is None or region.id != exclude_region_id)
        )

    async def list_regions(self, *, enabled_only: bool = False) -> list[RegionConfig]:
        regions = list(self.regions.values())
        return [region for region in regions if region.enabled] if enabled_only else regions

    async def has_dependent_plans(self, region_code: str) -> bool:
        return region_code in self.dependent_region_codes

    async def delete_region(self, region_id: UUID) -> bool:
        return self.regions.pop(region_id, None) is not None


class FakeMaintenanceRepository:
    def __init__(self) -> None:
        self.windows: dict[UUID, MaintenanceWindow] = {}

    async def find_overlapping_windows(
        self,
        *,
        starts_at: datetime,
        ends_at: datetime,
        exclude_id: UUID | None = None,
    ) -> list[MaintenanceWindow]:
        return [
            window
            for window in self.windows.values()
            if window.status in {"scheduled", "active"}
            and window.id != exclude_id
            and window.starts_at < ends_at
            and window.ends_at > starts_at
        ]

    async def insert_window(self, **kwargs: Any) -> MaintenanceWindow:
        window = _window(
            status="scheduled",
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

    async def update_window_status(
        self, window_id: UUID, *, status: str, **fields: Any
    ) -> MaintenanceWindow | None:
        window = self.windows.get(window_id)
        if window is None:
            return None
        window.status = status
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
        return window

    async def get_active_window(self) -> MaintenanceWindow | None:
        return next((window for window in self.windows.values() if window.status == "active"), None)

    async def list_windows(
        self,
        *,
        status: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[MaintenanceWindow]:
        del since, until
        return [
            window
            for window in self.windows.values()
            if status is None or window.status == status
        ]


class FakeFailoverRepository(FakeRegionRepository):
    def __init__(self) -> None:
        super().__init__()
        self.regions = {
            uuid4(): _region("eu-west", "primary"),
            uuid4(): _region("us-east", "secondary"),
        }
        self.plans: dict[UUID, FailoverPlan] = {}
        self.runs: dict[UUID, FailoverPlanRun] = {}
        self.in_progress = False

    async def insert_plan(self, **kwargs: Any) -> FailoverPlan:
        plan = _plan(steps=kwargs["steps"])
        plan.name = kwargs["name"]
        plan.from_region = kwargs["from_region"]
        plan.to_region = kwargs["to_region"]
        plan.runbook_url = kwargs["runbook_url"]
        plan.created_by = kwargs["created_by"]
        self.plans[plan.id] = plan
        return plan

    async def get_plan(self, plan_id: UUID) -> FailoverPlan | None:
        return self.plans.get(plan_id)

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
        self, plan_id: UUID, *, expected_version: int, updates: dict[str, Any]
    ) -> FailoverPlan | None:
        plan = self.plans.get(plan_id)
        if plan is None or plan.version != expected_version:
            return None
        for key, value in updates.items():
            if value is not None:
                setattr(plan, key, value)
        plan.version += 1
        return plan

    async def has_in_progress_runs(self, plan_id: UUID) -> bool:
        del plan_id
        return self.in_progress

    async def delete_plan(self, plan_id: UUID) -> bool:
        return self.plans.pop(plan_id, None) is not None

    async def insert_plan_run(self, **kwargs: Any) -> FailoverPlanRun:
        run = _run(kwargs["plan_id"])
        run.run_kind = kwargs["run_kind"]
        run.initiated_by = kwargs["initiated_by"]
        run.reason = kwargs["reason"]
        run.lock_token = kwargs["lock_token"]
        self.runs[run.id] = run
        return run

    async def append_plan_run_step_outcome(
        self, run_id: UUID, step_outcome: dict[str, Any]
    ) -> FailoverPlanRun | None:
        run = self.runs.get(run_id)
        if run is None:
            return None
        run.step_outcomes = [*run.step_outcomes, step_outcome]
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

    async def get_plan_run(self, run_id: UUID) -> FailoverPlanRun | None:
        return self.runs.get(run_id)

    async def list_plan_runs(self, plan_id: UUID) -> list[FailoverPlanRun]:
        return [run for run in self.runs.values() if run.plan_id == plan_id]

    async def get_latest_in_progress_run(self, *, from_region: str, to_region: str) -> Any:
        del from_region, to_region
        return next(iter(self.runs.values()), None)

    async def mark_plan_tested(self, plan_id: UUID, ts: datetime) -> None:
        self.plans[plan_id].tested_at = ts

    async def mark_plan_executed(self, plan_id: UUID, ts: datetime) -> None:
        self.plans[plan_id].last_executed_at = ts


class RecordingStepAdapter:
    kind = "custom"

    def __init__(self, outcome: str = "succeeded") -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    async def execute(
        self,
        *,
        plan: FailoverPlan,
        run: FailoverPlanRun,
        parameters: dict[str, Any],
        dry_run: bool = False,
    ) -> StepOutcome:
        self.calls.append({"plan": plan, "run": run, "parameters": parameters, "dry_run": dry_run})
        return StepOutcome(
            kind=self.kind,
            name=str(parameters["name"]),
            outcome=self.outcome,
            error_detail="boom" if self.outcome == "failed" else None,
        )


@pytest.mark.asyncio
async def test_region_service_lifecycle_and_active_active_guard() -> None:
    repository = FakeRegionRepository()
    audit = FakeAudit()
    service = RegionService(repository=repository, audit_chain_service=audit)  # type: ignore[arg-type]

    primary = await service.create(
        RegionConfigCreateRequest(region_code="eu-west", region_role=RegionRole.primary),
        by_user_id=uuid4(),
    )
    with pytest.raises(ActiveActiveConfigurationRefusedError):
        await service.create(
            RegionConfigCreateRequest(region_code="us-east", region_role=RegionRole.primary)
        )

    updated = await service.update(
        primary.id,
        RegionConfigUpdateRequest(region_code="eu-central", enabled=False),
    )
    enabled = await service.enable(updated.id)
    disabled = await service.disable(updated.id)

    assert enabled.enabled is False
    assert disabled.enabled is False
    assert await service.get_by_code("eu-central") is disabled
    assert await service.list(enabled_only=False) == [disabled]
    assert audit.entries

    repository.dependent_region_codes.add("eu-central")
    with pytest.raises(ValueError, match="referenced by failover plans"):
        await service.delete(disabled.id)
    repository.dependent_region_codes.clear()
    await service.delete(disabled.id)
    with pytest.raises(RegionNotFoundError):
        await service.get(disabled.id)

    no_audit_service = RegionService(repository=FakeRegionRepository())  # type: ignore[arg-type]
    secondary = await no_audit_service.create(
        RegionConfigCreateRequest(region_code="ap-south", region_role=RegionRole.secondary)
    )
    assert secondary.region_code == "ap-south"

    with pytest.raises(RegionNotFoundError):
        await no_audit_service.update(uuid4(), RegionConfigUpdateRequest(region_code="missing"))
    with pytest.raises(RegionNotFoundError):
        await no_audit_service.enable(uuid4())
    with pytest.raises(RegionNotFoundError):
        await no_audit_service.disable(uuid4())
    with pytest.raises(RegionNotFoundError):
        await no_audit_service.delete(uuid4())
    with pytest.raises(RegionNotFoundError):
        await no_audit_service.get_by_code("missing")

    class VanishingRegionRepository(FakeRegionRepository):
        async def update_region(self, region_id: UUID, **updates: Any) -> RegionConfig | None:
            del region_id, updates
            return None

    vanishing_repository = VanishingRegionRepository()
    vanishing_region = _region("ca-central")
    vanishing_repository.regions[vanishing_region.id] = vanishing_region
    vanishing_service = RegionService(repository=vanishing_repository)  # type: ignore[arg-type]
    with pytest.raises(RegionNotFoundError):
        await vanishing_service.update(
            vanishing_region.id,
            RegionConfigUpdateRequest(region_code="ca-central-1"),
        )
    with pytest.raises(RegionNotFoundError):
        await vanishing_service.enable(vanishing_region.id)
    with pytest.raises(RegionNotFoundError):
        await vanishing_service.disable(vanishing_region.id)


@pytest.mark.asyncio
async def test_maintenance_service_schedule_cache_disable_and_failure_paths() -> None:
    repository = FakeMaintenanceRepository()
    redis = FakeRedis()
    producer = FakeProducer()
    incidents = FakeIncidentTrigger()
    audit = FakeAudit()
    service = MaintenanceModeService(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        redis_client=redis,  # type: ignore[arg-type]
        producer=producer,  # type: ignore[arg-type]
        incident_trigger=incidents,  # type: ignore[arg-type]
        audit_chain_service=audit,  # type: ignore[arg-type]
    )
    starts = _now() + timedelta(minutes=30)
    payload = MaintenanceWindowCreateRequest(
        starts_at=starts,
        ends_at=starts + timedelta(minutes=30),
        reason="database failover rehearsal",
        announcement_text="Maintenance window",
    )

    with pytest.raises(MaintenanceWindowInPastError):
        await service.schedule(
            MaintenanceWindowCreateRequest(
                starts_at=_now() - timedelta(minutes=1),
                ends_at=_now() + timedelta(minutes=5),
            )
        )
    window = await service.schedule(payload, by_user_id=uuid4())
    with pytest.raises(MaintenanceWindowOverlapError):
        await service.schedule(payload)

    later = starts + timedelta(hours=2)
    updated = await service.update(
        window.id,
        MaintenanceWindowUpdateRequest(starts_at=later, ends_at=later + timedelta(minutes=45)),
    )
    active = await service.enable(updated.id)
    cached = await service.get_active_window()
    banner = service.status_banner(cached)
    disabled = await service.disable(active.id, disable_kind="scheduled")

    assert cached is not None
    assert cached.id == active.id
    assert banner is not None
    assert banner["window_id"] == str(active.id)
    assert disabled.status == "completed"
    assert REDIS_KEY_ACTIVE_WINDOW not in redis.values
    assert [event["event_type"] for event in producer.events] == [
        "maintenance.mode.enabled",
        "maintenance.mode.disabled",
    ]
    assert audit.entries

    failing_window = _window(status="active")
    repository.windows[failing_window.id] = failing_window
    failing_service = MaintenanceModeService(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        redis_client=FakeRedis(fail_delete=True),  # type: ignore[arg-type]
        incident_trigger=incidents,  # type: ignore[arg-type]
    )
    with pytest.raises(MaintenanceDisableFailedError):
        await failing_service.disable(failing_window.id)
    assert failing_window.disable_failure_reason == "redis unavailable"
    assert incidents.signals[-1].condition_fingerprint == f"maintenance:disable:{failing_window.id}"

    cancelled = _window()
    repository.windows[cancelled.id] = cancelled
    assert (await service.cancel(cancelled.id)).status == "cancelled"
    assert await service.list_windows(status="cancelled") == [cancelled]
    assert service.status_banner(None) is None


@pytest.mark.asyncio
async def test_maintenance_service_error_edges_and_cache_helpers() -> None:
    repository = FakeMaintenanceRepository()
    service = MaintenanceModeService(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(),
    )
    missing_id = uuid4()

    with pytest.raises(MaintenanceWindowNotFoundError):
        await service.update(missing_id, MaintenanceWindowUpdateRequest(reason="missing"))
    with pytest.raises(MaintenanceWindowNotFoundError):
        await service.enable(missing_id)
    with pytest.raises(MaintenanceWindowNotFoundError):
        await service.disable(missing_id)
    with pytest.raises(MaintenanceWindowNotFoundError):
        await service.cancel(missing_id)

    active = _window(status="active")
    repository.windows[active.id] = active
    with pytest.raises(ValueError, match="modified"):
        await service.update(active.id, MaintenanceWindowUpdateRequest(reason="nope"))
    with pytest.raises(ValueError, match="cancelled"):
        await service.cancel(active.id)

    scheduled = _window()
    repository.windows[scheduled.id] = scheduled
    with pytest.raises(MaintenanceWindowInPastError):
        await service.update(
            scheduled.id,
            MaintenanceWindowUpdateRequest(
                starts_at=_now() - timedelta(minutes=2),
                ends_at=_now() + timedelta(minutes=10),
            ),
        )
    overlapping = _window(
        starts_at=scheduled.starts_at + timedelta(minutes=5),
        ends_at=scheduled.ends_at + timedelta(minutes=5),
    )
    repository.windows[overlapping.id] = overlapping
    with pytest.raises(MaintenanceWindowOverlapError):
        await service.update(
            scheduled.id,
            MaintenanceWindowUpdateRequest(
                starts_at=overlapping.starts_at,
                ends_at=overlapping.ends_at,
            ),
        )

    class DropWindowRepository(FakeMaintenanceRepository):
        async def update_window(self, window_id: UUID, **fields: Any) -> MaintenanceWindow | None:
            del window_id, fields
            return None

    drop_window_repository = DropWindowRepository()
    drop_window = _window()
    drop_window_repository.windows[drop_window.id] = drop_window
    drop_window_service = MaintenanceModeService(
        repository=drop_window_repository,  # type: ignore[arg-type]
        settings=PlatformSettings(),
    )
    with pytest.raises(MaintenanceWindowNotFoundError):
        await drop_window_service.update(
            drop_window.id,
            MaintenanceWindowUpdateRequest(reason="vanished"),
        )

    class DropStatusRepository(FakeMaintenanceRepository):
        async def update_window_status(
            self, window_id: UUID, *, status: str, **fields: Any
        ) -> MaintenanceWindow | None:
            del window_id, status, fields
            return None

    drop_status_repository = DropStatusRepository()
    drop_status_window = _window()
    drop_status_repository.windows[drop_status_window.id] = drop_status_window
    drop_status_service = MaintenanceModeService(
        repository=drop_status_repository,  # type: ignore[arg-type]
        settings=PlatformSettings(),
    )
    with pytest.raises(MaintenanceWindowNotFoundError):
        await drop_status_service.enable(drop_status_window.id)
    with pytest.raises(MaintenanceWindowNotFoundError):
        await drop_status_service.disable(drop_status_window.id)
    with pytest.raises(MaintenanceWindowNotFoundError):
        await drop_status_service.cancel(drop_status_window.id)

    cache_miss_redis = FakeRedis()
    active_repository = FakeMaintenanceRepository()
    active_window = _window(status="active")
    active_repository.windows[active_window.id] = active_window
    cached_service = MaintenanceModeService(
        repository=active_repository,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        redis_client=cache_miss_redis,  # type: ignore[arg-type]
    )
    assert await cached_service.get_active_window() is active_window
    assert REDIS_KEY_ACTIVE_WINDOW in cache_miss_redis.values

    await service._prime_active_cache(active_window)
    assert await service._read_active_cache() is None
    await service._clear_active_cache()
    await service._fire_disable_failed_incident(active_window, "ignored")
    await service._audit("multi_region_ops.noop", {})
    assert maintenance_aware(_now().replace(tzinfo=None)).tzinfo is UTC

    cached = _window_from_cache(
        {
            "id": str(active_window.id),
            "scheduled_by": str(uuid4()),
            "starts_at": active_window.starts_at.isoformat(),
            "ends_at": active_window.ends_at.isoformat(),
            "created_at": active_window.created_at.isoformat(),
            "updated_at": active_window.updated_at.isoformat(),
        }
    )
    assert cached.id == active_window.id
    assert cached.scheduled_by is not None


@pytest.mark.asyncio
async def test_failover_service_runs_plans_and_records_aborted_steps() -> None:
    repository = FakeFailoverRepository()
    audit = FakeAudit()
    producer = FakeProducer()
    adapter = RecordingStepAdapter()
    service = FailoverService(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        producer=producer,  # type: ignore[arg-type]
        audit_chain_service=audit,  # type: ignore[arg-type]
        step_adapters={"custom": adapter},  # type: ignore[arg-type]
    )
    create_payload = FailoverPlanCreateRequest(
        name="primary-to-dr",
        from_region="eu-west",
        to_region="us-east",
        steps=[FailoverPlanStep(kind="custom", name="Notify")],
    )
    plan = await service.create_plan(create_payload, by_user_id=uuid4())
    updated = await service.update_plan(
        plan.id,
        FailoverPlanUpdateRequest(
            expected_version=1,
            name="primary-to-dr-v2",
            steps=[FailoverPlanStep(kind="custom", name="Notify again")],
        ),
    )
    run = await service.rehearse(updated.id, reason="quarterly exercise")

    assert run.outcome == "succeeded"
    assert updated.tested_at is not None
    assert await service.get_run(run.id) is run
    assert await service.list_runs(updated.id) == [run]
    assert await service.list_plans(from_region="eu-west") == [updated]
    assert service.is_stale(_plan()) is True
    assert adapter.calls[0]["dry_run"] is True
    assert {event["event_type"] for event in producer.events} == {
        "region.failover.initiated",
        "region.failover.completed",
    }
    assert audit.entries

    failing_plan = _plan(
        steps=[
            {"kind": "custom", "name": "Stop here", "parameters": {}},
            {"kind": "custom", "name": "Skipped", "parameters": {}},
        ]
    )
    repository.plans[failing_plan.id] = failing_plan
    failing_service = FailoverService(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        step_adapters={"custom": RecordingStepAdapter("failed")},  # type: ignore[arg-type]
    )
    failed_run = await failing_service.execute(failing_plan.id)

    assert failed_run.outcome == "failed"
    assert [item["outcome"] for item in failed_run.step_outcomes] == ["failed", "aborted"]

    repository.in_progress = True
    with pytest.raises(FailoverInProgressError):
        await service.delete_plan(updated.id)
    repository.in_progress = False
    await service.delete_plan(updated.id)


@pytest.mark.asyncio
async def test_failover_service_not_found_lock_and_adapter_edges() -> None:
    repository = FakeFailoverRepository()
    service = FailoverService(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        step_adapters={"custom": RecordingStepAdapter()},  # type: ignore[arg-type]
    )
    missing_id = uuid4()

    with pytest.raises(FailoverPlanNotFoundError):
        await service.update_plan(
            missing_id,
            FailoverPlanUpdateRequest(expected_version=1, name="missing"),
        )
    with pytest.raises(FailoverPlanNotFoundError):
        await service.get_plan(missing_id)
    with pytest.raises(FailoverPlanNotFoundError):
        await service.delete_plan(missing_id)
    with pytest.raises(FailoverRunNotFoundError):
        await service.get_run(uuid4())

    plan = _plan()
    repository.plans[plan.id] = plan
    with pytest.raises(FailoverPlanNotFoundError):
        await service.update_plan(
            plan.id,
            FailoverPlanUpdateRequest(expected_version=99, name="wrong-version"),
        )

    plan.tested_at = _now()
    assert service.is_stale(plan) is False

    disabled_region = next(
        region for region in repository.regions.values() if region.region_code == "us-east"
    )
    disabled_region.enabled = False
    with pytest.raises(ValueError, match="not enabled"):
        await service.create_plan(
            FailoverPlanCreateRequest(
                name="disabled-target",
                from_region="eu-west",
                to_region="us-east",
                steps=[FailoverPlanStep(kind="custom", name="Notify")],
            )
        )
    disabled_region.enabled = True

    production_plan = _plan()
    repository.plans[production_plan.id] = production_plan
    production_run = await service.execute(production_plan.id, reason="incident")
    assert production_run.outcome == "succeeded"
    assert production_plan.last_executed_at is not None

    unknown_plan = _plan(steps=[{"kind": "unknown", "name": "Mystery", "parameters": {}}])
    repository.plans[unknown_plan.id] = unknown_plan
    unknown_run = await service.rehearse(unknown_plan.id)
    assert unknown_run.outcome == "failed"
    assert unknown_run.step_outcomes[0]["error_detail"] == "No adapter registered for unknown"

    class ExplodingAdapter:
        kind = "custom"

        async def execute(self, **kwargs: Any) -> StepOutcome:
            del kwargs
            raise RuntimeError("adapter exploded")

    exploding_service = FailoverService(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(),
        step_adapters={"custom": ExplodingAdapter()},  # type: ignore[arg-type]
    )
    exploded = await exploding_service._execute_step(
        production_plan,
        production_run,
        0,
        {"kind": "custom", "name": "Boom", "parameters": {}},
        dry_run=False,
    )
    assert exploded["outcome"] == "failed"
    assert exploded["error_detail"] == "adapter exploded"

    class LockedFailoverService(FailoverService):
        async def acquire_failover_lock(self, from_region: str, to_region: str) -> str | None:
            del from_region, to_region
            return None

    locked_run = _run(plan.id)
    repository.runs[locked_run.id] = locked_run
    locked_service = LockedFailoverService(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(),
    )
    with pytest.raises(FailoverInProgressError):
        await locked_service.rehearse(plan.id)


@pytest.mark.asyncio
async def test_failover_step_and_probe_helpers_cover_edge_cases() -> None:
    blocked = await NoopStepAdapter().execute(
        plan=None,  # type: ignore[arg-type]
        run=None,  # type: ignore[arg-type]
        parameters={"name": "DNS", "route": "production"},
        dry_run=True,
    )
    allowed = await NoopStepAdapter().execute(
        plan=None,  # type: ignore[arg-type]
        run=None,  # type: ignore[arg-type]
        parameters={},
    )

    assert blocked.outcome == "failed"
    assert allowed.outcome == "succeeded"
    assert _interval_to_seconds(None) is None
    assert _interval_to_seconds(timedelta(seconds=65)) == 65
    assert _interval_to_seconds("01:02:03") == 3723
    assert _interval_to_seconds("bad") is None
    assert _extract_kafka_lag({"lag_seconds": 3}) == 3
    assert _extract_kafka_lag([{"lag": 4}, {"lag_seconds": 6}]) == 10
    assert _extract_kafka_lag(object()) == 0
    assert _as_int("42.8") == 42
    assert _as_int("bad") is None
    assert _extract_qdrant_lag({"peers": {"a": {"lag_seconds": 3}, "b": {"lag_seconds": 9}}}) == 9
    assert _extract_shard_lag({"shards": {"total": 5, "successful": 3}}) == 2
    assert _extract_s3_lag({"Metrics": {"ReplicationLatency": 7}}) == 7
    assert _extract_tx_lag([{"last_committed_tx": 10}, {"lastCommittedTx": 15}]) == 5

    source = _region("eu-west", "primary")
    target = _region("us-east")
    secret_provider = SimpleNamespace(get_current=lambda ref: ref)
    postgres = await PostgresReplicationProbe(secret_provider).measure(  # type: ignore[arg-type]
        source=source, target=target
    )
    kafka = await KafkaReplicationProbe(secret_provider).measure(  # type: ignore[arg-type]
        source=source, target=target
    )
    s3 = await S3ReplicationProbe(secret_provider).measure(  # type: ignore[arg-type]
        source=source, target=target
    )
    clickhouse = await ClickHouseReplicationProbe(None).measure(source=source, target=target)
    qdrant = await QdrantReplicationProbe(secret_provider).measure(  # type: ignore[arg-type]
        source=source, target=target
    )
    neo4j = await Neo4jReplicationProbe(secret_provider).measure(  # type: ignore[arg-type]
        source=source, target=target
    )
    opensearch = await OpenSearchReplicationProbe(secret_provider).measure(  # type: ignore[arg-type]
        source=source, target=target
    )
    assert postgres.error_detail == "postgres_replica_dsn_ref missing"
    assert kafka.error_detail == "mirrormaker_consumer_group missing"
    assert s3.error_detail == "s3_bucket missing"
    assert clickhouse.error_detail == "clickhouse client unavailable"
    assert qdrant.error_detail == "qdrant_cluster_url missing"
    assert neo4j.error_detail == "neo4j_uri missing"
    assert opensearch.error_detail == "opensearch_url missing"
    assert await _secret_or_value(secret_provider, None, "literal") == "literal"  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        ReplicationMeasurement(component="unknown", health="healthy")
    with pytest.raises(ValidationError):
        ReplicationMeasurement(component="postgres", health="unknown")


class AsyncSecretProvider:
    async def get_current(self, ref: str) -> str:
        return f"secret:{ref}"


class FakeHttpResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeHttpClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    async def __aenter__(self) -> FakeHttpClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, url: str, *, headers: dict[str, str]) -> FakeHttpResponse:
        assert url
        assert isinstance(headers, dict)
        return FakeHttpResponse(self.payload)


@pytest.mark.asyncio
async def test_replication_probe_success_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    source = _region(
        "eu-west",
        "primary",
        endpoints={"postgres_replica_dsn_ref": "pg-dsn"},
    )
    target = _region(
        "us-east",
        endpoints={
            "mirrormaker_consumer_group": "mirror",
            "kafka_admin_brokers_ref": "brokers",
            "s3_bucket": "replica",
            "s3_endpoint_url_ref": "s3-endpoint",
            "s3_access_key_ref": "s3-access",
            "s3_secret_key_ref": "s3-secret",
            "qdrant_cluster_url": "https://qdrant.example",
            "qdrant_api_key_ref": "qdrant-key",
            "neo4j_uri": "bolt://neo4j.example",
            "neo4j_user": "neo4j",
            "neo4j_password": "password",
            "opensearch_url": "https://opensearch.example",
            "opensearch_api_key_ref": "opensearch-key",
        },
    )
    secrets = AsyncSecretProvider()

    asyncpg = ModuleType("asyncpg")

    class FakePgConnection:
        async def fetch(self, query: str) -> list[dict[str, Any]]:
            assert "pg_stat_replication" in query
            return [{"state": "catchup", "replay_lag": timedelta(seconds=8)}]

        async def close(self) -> None:
            return None

    async def connect(dsn: str) -> FakePgConnection:
        assert dsn == "secret:pg-dsn"
        return FakePgConnection()

    asyncpg.connect = connect  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "asyncpg", asyncpg)

    aiokafka = ModuleType("aiokafka")
    aiokafka_admin = ModuleType("aiokafka.admin")

    class FakeAdmin:
        def __init__(self, *, bootstrap_servers: str, request_timeout_ms: int) -> None:
            assert bootstrap_servers == "secret:brokers"
            assert request_timeout_ms > 0

        async def start(self) -> None:
            return None

        async def describe_consumer_groups(self, groups: list[str]) -> list[dict[str, int]]:
            assert groups == ["mirror"]
            return [{"lag": 2}, {"lag_seconds": 3}]

        async def stop(self) -> None:
            return None

    aiokafka_admin.AIOKafkaAdminClient = FakeAdmin  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "aiokafka", aiokafka)
    monkeypatch.setitem(sys.modules, "aiokafka.admin", aiokafka_admin)

    aioboto3 = ModuleType("aioboto3")

    class FakeS3Client:
        async def __aenter__(self) -> FakeS3Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get_bucket_replication(self, **kwargs: str) -> dict[str, Any]:
            assert kwargs["Bucket"] == "replica"
            return {"metrics": {"replication_latency_seconds": 12}}

    class FakeBotoSession:
        def client(self, service_name: str, **kwargs: Any) -> FakeS3Client:
            assert service_name == "s3"
            assert kwargs["endpoint_url"] == "secret:s3-endpoint"
            return FakeS3Client()

    aioboto3.Session = FakeBotoSession  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "aioboto3", aioboto3)

    neo4j = ModuleType("neo4j")

    class FakeAsyncRows:
        def __init__(self) -> None:
            self.rows = iter([{"last_committed_tx": 9}, {"lastCommittedTx": 15}])

        def __aiter__(self) -> FakeAsyncRows:
            return self

        async def __anext__(self) -> dict[str, int]:
            try:
                return next(self.rows)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class FakeNeo4jSession:
        async def __aenter__(self) -> FakeNeo4jSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def run(self, query: str) -> FakeAsyncRows:
            assert "cluster" in query
            return FakeAsyncRows()

    class FakeNeo4jDriver:
        def session(self) -> FakeNeo4jSession:
            return FakeNeo4jSession()

        async def close(self) -> None:
            return None

    neo4j.AsyncGraphDatabase = SimpleNamespace(  # type: ignore[attr-defined]
        driver=lambda uri, auth: FakeNeo4jDriver()
    )
    monkeypatch.setitem(sys.modules, "neo4j", neo4j)

    clickhouse_client = SimpleNamespace(
        execute_query=lambda query: [{"lag_seconds": "17", "queue_size": 3}]
    )

    async def execute_query(query: str) -> list[dict[str, str | int]]:
        assert "replication_queue" in query
        return [{"lag_seconds": "17", "queue_size": 3}]

    clickhouse_client.execute_query = execute_query

    postgres = await PostgresReplicationProbe(secrets).measure(  # type: ignore[arg-type]
        source=source, target=target
    )
    kafka = await KafkaReplicationProbe(secrets).measure(  # type: ignore[arg-type]
        source=source, target=target
    )
    s3 = await S3ReplicationProbe(secrets).measure(source=source, target=target)  # type: ignore[arg-type]
    clickhouse = await ClickHouseReplicationProbe(clickhouse_client).measure(  # type: ignore[arg-type]
        source=source, target=target
    )
    monkeypatch.setattr(
        qdrant_module.httpx,
        "AsyncClient",
        lambda timeout: FakeHttpClient({"peers": {"a": {"lag_seconds": 4}}}),
    )
    qdrant = await QdrantReplicationProbe(secrets).measure(  # type: ignore[arg-type]
        source=source, target=target
    )
    neo = await Neo4jReplicationProbe(secrets).measure(source=source, target=target)  # type: ignore[arg-type]
    monkeypatch.setattr(
        opensearch_module.httpx,
        "AsyncClient",
        lambda timeout: FakeHttpClient({"shards": {"total": 8, "successful": 7}}),
    )
    opensearch = await OpenSearchReplicationProbe(secrets).measure(  # type: ignore[arg-type]
        source=source, target=target
    )

    assert postgres.health == "degraded"
    assert kafka.lag_seconds == 5
    assert s3.lag_seconds == 12
    assert clickhouse.health == "degraded"
    assert qdrant.lag_seconds == 4
    assert neo.lag_seconds == 6
    assert opensearch.lag_seconds == 1


@pytest.mark.asyncio
async def test_verify_health_step_and_maintenance_gate_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class HealthResponse:
        def __init__(self, *, raises: bool = False) -> None:
            self.raises = raises

        def raise_for_status(self) -> None:
            if self.raises:
                raise RuntimeError("health check failed")

    class HealthClient:
        def __init__(self, response: HealthResponse) -> None:
            self.response = response

        async def __aenter__(self) -> HealthClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str) -> HealthResponse:
            assert url == "https://target.example/health"
            return self.response

    adapter = VerifyHealthStepAdapter()
    skipped = await adapter.execute(
        plan=None,  # type: ignore[arg-type]
        run=None,  # type: ignore[arg-type]
        parameters={},
    )
    monkeypatch.setattr(
        verify_health_module.httpx,
        "AsyncClient",
        lambda timeout: HealthClient(HealthResponse()),
    )
    succeeded = await adapter.execute(
        plan=None,  # type: ignore[arg-type]
        run=None,  # type: ignore[arg-type]
        parameters={"url": "https://target.example/health"},
    )
    monkeypatch.setattr(
        verify_health_module.httpx,
        "AsyncClient",
        lambda timeout: HealthClient(HealthResponse(raises=True)),
    )
    failed = await adapter.execute(
        plan=None,  # type: ignore[arg-type]
        run=None,  # type: ignore[arg-type]
        parameters={"name": "Target health", "url": "https://target.example/health"},
    )

    assert skipped.outcome == "succeeded"
    assert succeeded.outcome == "succeeded"
    assert failed.outcome == "failed"
    assert failed.error_detail == "health check failed"

    class RaisingGate(MaintenanceGateMiddleware):
        async def _active_window(self, request: Any) -> MaintenanceWindow | None:
            del request
            raise RuntimeError("database down")

    async def call_next(request: Any) -> Any:
        del request
        return SimpleNamespace(status_code=200)

    request = SimpleNamespace(
        method="POST",
        app=SimpleNamespace(
            state=SimpleNamespace(settings=PlatformSettings(feature_maintenance_mode=True))
        ),
    )
    raised_response = await RaisingGate(app=SimpleNamespace()).dispatch(request, call_next)
    assert raised_response.status_code == 200

    class PassiveGate(MaintenanceGateMiddleware):
        async def _active_window(self, request: Any) -> MaintenanceWindow | None:
            del request
            window = _window(status="active")
            window.blocks_writes = False
            return window

    passive_response = await PassiveGate(app=SimpleNamespace()).dispatch(request, call_next)
    assert passive_response.status_code == 200

    class RedisFailure:
        def __init__(self, raw: bytes | None = None) -> None:
            self.raw = raw
            self.values: dict[str, bytes] = {}

        async def get(self, key: str) -> bytes | None:
            assert key == REDIS_KEY_ACTIVE_WINDOW
            if self.raw is None:
                raise RuntimeError("redis unavailable")
            return self.raw

        async def set(self, key: str, value: bytes, *, ttl: int) -> None:
            assert ttl > 0
            self.values[key] = value

    class SessionContext:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *args: object) -> None:
            return None

    class WindowRepository:
        def __init__(self, session: object) -> None:
            del session

        async def get_active_window(self) -> MaintenanceWindow:
            return _window(status="active")

    monkeypatch.setattr(maintenance_gate_module.database, "AsyncSessionLocal", SessionContext)
    monkeypatch.setattr(maintenance_gate_module, "MultiRegionOpsRepository", WindowRepository)

    redis_failure = RedisFailure()
    active_request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(clients={"redis": redis_failure}))
    )
    window = await MaintenanceGateMiddleware(app=SimpleNamespace())._active_window(active_request)
    assert window is not None
    assert REDIS_KEY_ACTIVE_WINDOW in redis_failure.values

    decode_failure = RedisFailure(raw=b"{not-json")
    decode_request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(clients={"redis": decode_failure}))
    )
    assert await MaintenanceGateMiddleware(app=SimpleNamespace())._active_window(decode_request)


@pytest.mark.asyncio
async def test_capacity_dependency_and_middleware_helpers() -> None:
    class ForecastService:
        async def get_latest_forecast(self, workspace_id: UUID) -> Any:
            del workspace_id
            return SimpleNamespace(
                forecast_cents=100,
                confidence_interval={"status": "insufficient_history"},
            )

    class AnalyticsRepo:
        async def query_usage_rollups(self, *args: Any) -> tuple[list[dict[str, Any]], int]:
            assert args
            return ([{"resource_class": "compute", "value": 1}], 1)

    settings = PlatformSettings()
    workspace_id = uuid4()
    capacity = capacity_module.CapacityService(
        settings=settings,
        cost_governance_service=SimpleNamespace(forecast_service=ForecastService()),
        analytics_service=SimpleNamespace(repo=AnalyticsRepo()),
    )
    overview = await capacity.get_capacity_overview(workspace_id=workspace_id)
    recommendations = await capacity.active_recommendations(workspace_id=workspace_id)

    assert overview[0].historical_trend == [{"resource_class": "compute", "value": 1}]
    assert overview[0].confidence.value == "insufficient_history"
    assert recommendations == []

    redis = FakeRedis()
    window = _window(status="active")
    middleware = MaintenanceGateMiddleware(app=SimpleNamespace())
    await middleware._prime_cache(redis, window)
    assert REDIS_KEY_ACTIVE_WINDOW in redis.values
    assert middleware_aware(_now().replace(tzinfo=None)).tzinfo is UTC

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(settings=settings, clients={"redis": redis, "kafka": object()})
        )
    )
    provider = multi_region_dependencies.get_secret_provider(request)  # type: ignore[arg-type]
    assert multi_region_dependencies.get_secret_provider(request) is provider  # type: ignore[arg-type]
    registry = multi_region_dependencies.get_replication_probe_registry(  # type: ignore[arg-type]
        request, provider
    )
    assert set(registry.components()) == set(REPLICATION_COMPONENTS)
    assert multi_region_dependencies.get_redis_failover_lock(request) is redis  # type: ignore[arg-type]
    assert multi_region_dependencies.get_redis_active_window_cache(request) is redis  # type: ignore[arg-type]

    session = object()
    audit = object()
    incident_trigger = object()
    incident_service = object()
    region_service = await multi_region_dependencies.get_region_service(session, audit)  # type: ignore[arg-type]
    monitor = await multi_region_dependencies.get_replication_monitor(  # type: ignore[arg-type]
        request, session, registry, incident_trigger, incident_service
    )
    failover = await multi_region_dependencies.get_failover_service(  # type: ignore[arg-type]
        request, session, audit
    )
    maintenance = await multi_region_dependencies.get_maintenance_mode_service(  # type: ignore[arg-type]
        request, session, incident_trigger, audit
    )
    facade = await multi_region_dependencies.get_multi_region_ops_service(  # type: ignore[arg-type]
        region_service, monitor, failover, maintenance, capacity
    )
    assert facade.region_service is region_service


@pytest.mark.asyncio
async def test_capacity_service_alternate_forecast_and_rollup_sources() -> None:
    settings = PlatformSettings()
    workspace_id = uuid4()

    trigger = FakeIncidentTrigger()
    empty_service = capacity_module.CapacityService(settings=settings, incident_trigger=trigger)
    empty_signals = await empty_service.evaluate_saturation()
    assert empty_signals[0].projection is None
    assert trigger.signals == []

    class DirectForecastService:
        async def get_latest_forecast(self, workspace_id: UUID) -> Any:
            del workspace_id
            return SimpleNamespace(forecast_cents=200, confidence_interval={"status": "ok"})

    class DirectAnalytics:
        async def get_workspace_usage_rollups(self, workspace_id: UUID) -> list[dict[str, Any]]:
            del workspace_id
            return [{"resource_class": "compute", "value": 10}]

    direct_service = capacity_module.CapacityService(
        settings=settings,
        cost_governance_service=DirectForecastService(),
        analytics_service=DirectAnalytics(),
    )
    direct = await direct_service.get_capacity_overview(workspace_id=workspace_id)
    assert direct[0].historical_trend == [{"resource_class": "compute", "value": 10}]
    assert direct[0].recommendation is not None

    class RepositoryForecast:
        async def get_latest_forecast(self, workspace_id: UUID) -> Any:
            del workspace_id
            return SimpleNamespace(forecast_cents=None, confidence_interval={})

    class AnalyticsRepoError:
        async def query_usage_rollups(self, *args: Any) -> tuple[list[dict[str, Any]], int]:
            del args
            raise RuntimeError("analytics unavailable")

    repository_service = capacity_module.CapacityService(
        settings=settings,
        cost_governance_service=SimpleNamespace(repository=RepositoryForecast()),
        analytics_service=SimpleNamespace(repo=AnalyticsRepoError()),
    )
    repository_signals = await repository_service.get_capacity_overview(workspace_id=workspace_id)
    assert repository_signals[0].historical_trend == []
    assert repository_signals[0].projection["forecast_cents"] is None

    no_method_service = capacity_module.CapacityService(
        settings=settings,
        cost_governance_service=SimpleNamespace(repository=SimpleNamespace()),
        analytics_service=SimpleNamespace(repo=SimpleNamespace()),
    )
    assert await no_method_service.active_recommendations(workspace_id=workspace_id) == []


class FakeReplicationRepository:
    def __init__(self) -> None:
        self.regions = [_region("eu-west", "primary"), _region("us-east", "secondary", rpo=1)]
        self.rows: list[Any] = []
        self.over_threshold_components: set[str] = set()
        self.at_or_below = False

    async def list_regions(self, *, enabled_only: bool = False) -> list[RegionConfig]:
        if enabled_only:
            return [region for region in self.regions if region.enabled]
        return self.regions

    async def insert_replication_status(self, **kwargs: Any) -> Any:
        row = SimpleNamespace(id=uuid4(), **kwargs)
        self.rows.append(row)
        return row

    async def count_consecutive_over_threshold(
        self, *, component: str, **kwargs: Any
    ) -> bool:
        del kwargs
        return component in self.over_threshold_components

    async def count_consecutive_at_or_below_threshold(self, **kwargs: Any) -> bool:
        del kwargs
        return self.at_or_below


class FailingProbe:
    component = "postgres"

    async def measure(
        self, *, source: RegionConfig, target: RegionConfig
    ) -> ReplicationMeasurement:
        del source, target
        raise RuntimeError("probe failed")


class HealthyProbe:
    component = "postgres"

    async def measure(
        self, *, source: RegionConfig, target: RegionConfig
    ) -> ReplicationMeasurement:
        del source, target
        return ReplicationMeasurement(component="postgres", lag_seconds=0, health="healthy")


class FakeIncidentService:
    def __init__(self) -> None:
        self.repository = SimpleNamespace(find_open_incident_by_fingerprint=self._find)
        self.resolved: list[UUID] = []
        self.incident_id = uuid4()

    async def _find(self, fingerprint: str) -> Any:
        del fingerprint
        return SimpleNamespace(id=self.incident_id)

    async def resolve(self, incident_id: UUID, **kwargs: Any) -> None:
        del kwargs
        self.resolved.append(incident_id)


@pytest.mark.asyncio
async def test_replication_monitor_records_failures_alerts_and_resolutions() -> None:
    repository = FakeReplicationRepository()
    repository.over_threshold_components.add("postgres")
    registry = ReplicationProbeRegistry()
    registry.register(FailingProbe())
    trigger = FakeIncidentTrigger()
    producer = FakeProducer()
    monitor = ReplicationMonitor(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(feature_multi_region=True),
        probe_registry=registry,
        incident_trigger=trigger,  # type: ignore[arg-type]
        producer=producer,  # type: ignore[arg-type]
    )

    measurements = await monitor.probe_all()

    assert len(measurements) == len(REPLICATION_COMPONENTS)
    assert measurements[0].error_detail == "probe failed"
    assert trigger.signals[0].condition_fingerprint == replication_fingerprint(
        "postgres", "eu-west", "us-east"
    )
    assert len(repository.rows) == len(REPLICATION_COMPONENTS)
    assert producer.events

    off = ReplicationMonitor(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(feature_multi_region=False),
        probe_registry=registry,
        incident_trigger=trigger,  # type: ignore[arg-type]
    )
    assert await off.probe_all() == []

    repository.over_threshold_components.clear()
    repository.at_or_below = True
    registry = ReplicationProbeRegistry()
    registry.register(HealthyProbe())
    incident_service = FakeIncidentService()
    resolving = ReplicationMonitor(
        repository=repository,  # type: ignore[arg-type]
        settings=PlatformSettings(feature_multi_region=True),
        probe_registry=registry,
        incident_trigger=trigger,  # type: ignore[arg-type]
        incident_service=incident_service,  # type: ignore[arg-type]
    )
    await resolving._record_measurement(
        repository.regions[0],
        repository.regions[1],
        ReplicationMeasurement(component="postgres", lag_seconds=0, health="healthy"),
    )

    assert incident_service.resolved == [incident_service.incident_id]


@pytest.mark.asyncio
async def test_multi_region_facade_delegates_active_window() -> None:
    async def get_active_window() -> MaintenanceWindow:
        return _window(status="active")

    maintenance = SimpleNamespace(get_active_window=get_active_window)
    service = MultiRegionOpsService(
        region_service=SimpleNamespace(),  # type: ignore[arg-type]
        replication_monitor=SimpleNamespace(),  # type: ignore[arg-type]
        failover_service=SimpleNamespace(),  # type: ignore[arg-type]
        maintenance_mode_service=maintenance,  # type: ignore[arg-type]
        capacity_service=SimpleNamespace(),  # type: ignore[arg-type]
    )
    await service.handle_workspace_archived(uuid4())
    assert (await service.get_active_window()).status == "active"


def test_cached_window_payload_round_trips_like_redis() -> None:
    window = _window(status="active")
    payload = {
        "id": str(window.id),
        "starts_at": window.starts_at.isoformat(),
        "ends_at": window.ends_at.isoformat(),
        "reason": window.reason,
        "blocks_writes": window.blocks_writes,
        "announcement_text": window.announcement_text,
        "status": window.status,
        "scheduled_by": str(uuid4()),
        "enabled_at": _now().isoformat(),
        "disabled_at": None,
        "disable_failure_reason": None,
        "created_at": window.created_at.isoformat(),
        "updated_at": window.updated_at.isoformat(),
    }

    encoded = json.dumps(payload, separators=(",", ":")).encode()

    assert json.loads(encoded.decode())["id"] == str(window.id)
