from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.multi_region_ops.models import (
    FailoverPlan,
    FailoverPlanRun,
    MaintenanceWindow,
    RegionConfig,
    ReplicationStatus,
)
from platform.multi_region_ops.repository import MultiRegionOpsRepository
from typing import Any
from uuid import UUID, uuid4

import pytest


def _now() -> datetime:
    return datetime.now(UTC)


def _region(code: str = "eu-west", role: str = "primary", *, enabled: bool = True) -> RegionConfig:
    region = RegionConfig(
        region_code=code,
        region_role=role,
        endpoint_urls={},
        rpo_target_minutes=15,
        rto_target_minutes=60,
        enabled=enabled,
    )
    region.id = uuid4()
    region.created_at = _now()
    region.updated_at = region.created_at
    return region


def _status(
    component: str = "postgres",
    *,
    lag_seconds: int | None = 5,
    health: str = "healthy",
    measured_at: datetime | None = None,
) -> ReplicationStatus:
    status = ReplicationStatus(
        source_region="eu-west",
        target_region="us-east",
        component=component,
        lag_seconds=lag_seconds,
        health=health,
        measured_at=measured_at or _now(),
    )
    status.id = uuid4()
    return status


def _plan() -> FailoverPlan:
    plan = FailoverPlan(
        name="primary-to-dr",
        from_region="eu-west",
        to_region="us-east",
        steps=[{"kind": "custom", "name": "Notify", "parameters": {}}],
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


def _run(plan_id: UUID) -> FailoverPlanRun:
    run = FailoverPlanRun(
        plan_id=plan_id,
        run_kind="rehearsal",
        outcome="in_progress",
        started_at=_now(),
        step_outcomes=[],
        lock_token="token",
    )
    run.id = uuid4()
    run.ended_at = None
    run.initiated_by = None
    run.reason = None
    return run


def _window(status: str = "scheduled") -> MaintenanceWindow:
    starts_at = _now() + timedelta(minutes=5)
    window = MaintenanceWindow(
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        reason="maintenance",
        blocks_writes=True,
        announcement_text=None,
        status=status,
        created_at=_now(),
        updated_at=_now(),
    )
    window.id = uuid4()
    return window


class FakeScalarRows:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


class FakeResult:
    def __init__(self, *, rows: list[Any] | None = None, scalar: Any = None) -> None:
        self.rows = rows or []
        self.scalar = scalar

    def scalar_one(self) -> Any:
        return self.scalar

    def scalar_one_or_none(self) -> Any:
        return self.scalar

    def scalars(self) -> FakeScalarRows:
        return FakeScalarRows(self.rows)


class FakeSession:
    def __init__(self) -> None:
        self.results: list[FakeResult] = []
        self.objects: dict[tuple[type[Any], UUID], Any] = {}
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.flushed = 0

    def queue(self, *results: FakeResult) -> None:
        self.results.extend(results)

    def add(self, item: Any) -> None:
        self.added.append(item)
        item_id = getattr(item, "id", None)
        if isinstance(item_id, UUID):
            self.objects[(type(item), item_id)] = item

    async def flush(self) -> None:
        self.flushed += 1

    async def refresh(self, item: Any) -> None:
        del item

    async def get(self, model: type[Any], object_id: UUID) -> Any:
        return self.objects.get((model, object_id))

    async def delete(self, item: Any) -> None:
        self.deleted.append(item)
        item_id = getattr(item, "id", None)
        if isinstance(item_id, UUID):
            self.objects.pop((type(item), item_id), None)

    async def execute(self, statement: Any) -> FakeResult:
        del statement
        if self.results:
            return self.results.pop(0)
        return FakeResult()


@pytest.mark.asyncio
async def test_repository_region_replication_plan_and_window_paths() -> None:
    session = FakeSession()
    repository = MultiRegionOpsRepository(session)  # type: ignore[arg-type]
    region = _region()
    secondary = _region("us-east", "secondary")
    plan = _plan()
    run = _run(plan.id)
    window = _window()
    active_window = _window("active")
    session.objects.update(
        {
            (RegionConfig, region.id): region,
            (FailoverPlan, plan.id): plan,
            (FailoverPlanRun, run.id): run,
            (MaintenanceWindow, window.id): window,
        }
    )

    inserted = await repository.insert_region(
        region_code="ap-south",
        region_role="secondary",
        endpoint_urls={},
        rpo_target_minutes=5,
        rto_target_minutes=20,
        enabled=True,
    )
    assert inserted.region_code == "ap-south"
    assert await repository.get_region(region.id) is region

    session.queue(
        FakeResult(scalar=secondary),
        FakeResult(rows=[region, secondary]),
        FakeResult(rows=[secondary]),
        FakeResult(scalar=1),
        FakeResult(scalar=1),
    )
    assert await repository.get_region_by_code("us-east") is secondary
    assert await repository.list_regions() == [region, secondary]
    assert await repository.list_regions(enabled_only=True) == [secondary]
    assert await repository.count_active_primaries() == 1
    assert await repository.has_dependent_plans("eu-west") is True

    updated_region = await repository.update_region(region.id, region_code="eu-central")
    assert updated_region is region
    assert region.region_code == "eu-central"
    assert await repository.delete_region(region.id) is True
    assert await repository.delete_region(uuid4()) is False

    newer = _status("postgres", measured_at=_now())
    older = _status("postgres", measured_at=_now() - timedelta(minutes=1))
    kafka = _status("kafka")
    session.queue(
        FakeResult(rows=[newer, older, kafka]),
        FakeResult(rows=[newer]),
        FakeResult(rows=[]),
        FakeResult(rows=[_status(lag_seconds=20), _status(lag_seconds=30)]),
        FakeResult(rows=[_status(lag_seconds=0), _status(lag_seconds=1)]),
    )
    status = await repository.insert_replication_status(
        source_region="eu-west",
        target_region="us-east",
        component="postgres",
        lag_seconds=1,
        health="healthy",
    )
    assert status.health == "healthy"
    assert await repository.get_latest_per_tuple() == [newer, kafka]
    assert await repository.list_replication_statuses_window(
        source="eu-west",
        target="us-east",
        component="postgres",
        since=_now() - timedelta(minutes=5),
        until=_now(),
    ) == [newer]
    assert await repository.count_consecutive_over_threshold(
        source="eu-west",
        target="us-east",
        component="postgres",
        threshold_seconds=10,
        n=2,
    ) is False
    assert await repository.count_consecutive_over_threshold(
        source="eu-west",
        target="us-east",
        component="postgres",
        threshold_seconds=10,
        n=2,
    ) is True
    assert await repository.count_consecutive_at_or_below_threshold(
        source="eu-west",
        target="us-east",
        component="postgres",
        threshold_seconds=10,
        n=2,
    ) is True

    session.queue(
        FakeResult(scalar=plan),
        FakeResult(rows=[plan]),
        FakeResult(scalar=1),
        FakeResult(rows=[run]),
        FakeResult(scalar=run),
        FakeResult(),
        FakeResult(),
        FakeResult(scalar=active_window),
        FakeResult(rows=[window]),
        FakeResult(rows=[active_window]),
    )
    inserted_plan = await repository.insert_plan(
        name="plan",
        from_region="eu-west",
        to_region="us-east",
        steps=[],
        runbook_url=None,
        created_by=None,
    )
    assert inserted_plan.name == "plan"
    assert await repository.get_plan(plan.id) is plan
    assert await repository.get_plan_by_name("primary-to-dr") is plan
    assert await repository.list_plans(from_region="eu-west", to_region="us-east") == [plan]
    assert await repository.update_plan(plan.id, expected_version=1, updates={"name": "renamed"})
    assert await repository.update_plan(plan.id, expected_version=1, updates={}) is None
    assert await repository.has_in_progress_runs(plan.id) is True

    inserted_run = await repository.insert_plan_run(
        plan_id=plan.id,
        run_kind="production",
        initiated_by=None,
        reason="incident",
        lock_token="abc",
    )
    assert inserted_run.outcome == "in_progress"
    assert await repository.update_plan_run_outcome(run.id, outcome="succeeded", ended_at=_now())
    assert await repository.append_plan_run_step_outcome(run.id, {"outcome": "succeeded"})
    assert run.step_outcomes == [{"outcome": "succeeded"}]
    assert await repository.get_plan_run(run.id) is run
    assert await repository.list_plan_runs(plan.id) == [run]
    assert await repository.get_latest_in_progress_run(
        from_region="eu-west", to_region="us-east"
    ) is run
    await repository.mark_plan_tested(plan.id, _now())
    await repository.mark_plan_executed(plan.id, _now())
    assert await repository.delete_plan(plan.id) is True
    assert await repository.delete_plan(uuid4()) is False

    inserted_window = await repository.insert_window(
        starts_at=_now() + timedelta(minutes=10),
        ends_at=_now() + timedelta(minutes=40),
        reason="maintenance",
        blocks_writes=True,
        announcement_text="notice",
        scheduled_by=None,
    )
    assert inserted_window.status == "scheduled"
    assert await repository.get_window(window.id) is window
    assert await repository.get_active_window() is active_window
    assert await repository.list_windows(status="scheduled") == [window]
    assert await repository.update_window_status(window.id, status="active")
    assert await repository.update_window(window.id, reason="updated")
    assert await repository.find_overlapping_windows(
        starts_at=_now(),
        ends_at=_now() + timedelta(hours=1),
        exclude_id=uuid4(),
    ) == [active_window]
