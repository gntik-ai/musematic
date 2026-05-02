from __future__ import annotations

from platform.billing.subscriptions import period_scheduler
from platform.common.config import PlatformSettings
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.unit.billing.quotas.test_runtime_coverage import _Session, _plan, _subscription


@pytest.mark.asyncio
async def test_data_exceeding_free_limits_workspace_and_tenant_paths() -> None:
    plan = _plan()
    workspace_subscription = _subscription(plan)
    owner_id = uuid4()
    workspace_session = _Session(scalar_results=[owner_id, 3, 8, 5])

    workspace_cleanup = await period_scheduler._data_exceeding_free_limits(
        workspace_session,
        workspace_subscription,
    )

    tenant_subscription = _subscription(plan)
    tenant_subscription.scope_type = "tenant"
    tenant_session = _Session(scalar_results=[4])
    tenant_cleanup = await period_scheduler._data_exceeding_free_limits(
        tenant_session,
        tenant_subscription,
    )

    assert workspace_cleanup == {"workspaces": 2, "agents": 3, "users": 2}
    assert tenant_cleanup == {"workspaces": 3, "agents": 0, "users": 0}
    assert await period_scheduler._data_exceeding_free_limits(
        _Session(scalar_results=[None, 0, 0]),
        workspace_subscription,
    ) == {"workspaces": 0, "agents": 0, "users": 0}
    assert await period_scheduler._plan_slug(_Session(scalar_results=[None]), uuid4()) == "unknown"


@pytest.mark.asyncio
async def test_build_period_rollover_scheduler_success_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        period_scheduler,
        "__import__",
        lambda *args, **kwargs: (_ for _ in ()).throw(ImportError("missing")),
        raising=False,
    )
    assert period_scheduler.build_period_rollover_scheduler(SimpleNamespace()) is None

    class _Scheduler:
        def __init__(self, timezone: str) -> None:
            self.timezone = timezone
            self.jobs: list[tuple[object, str, dict[str, object]]] = []

        def add_job(self, func: object, trigger: str, **kwargs: object) -> None:
            self.jobs.append((func, trigger, kwargs))

    monkeypatch.setattr(
        period_scheduler,
        "__import__",
        lambda *args, **kwargs: SimpleNamespace(AsyncIOScheduler=_Scheduler),
        raising=False,
    )
    scheduler = period_scheduler.build_period_rollover_scheduler(
        SimpleNamespace(
            state=SimpleNamespace(
                settings=PlatformSettings(BILLING_PERIOD_SCHEDULER_INTERVAL_SECONDS=17)
            )
        )
    )

    assert scheduler.timezone == "UTC"
    assert scheduler.jobs[0][1] == "interval"
    assert scheduler.jobs[0][2]["seconds"] == 17
    assert scheduler.jobs[0][2]["id"] == "billing.period_rollover"
    called: list[object] = []

    async def _run_period_rollover(app: object) -> None:
        called.append(app)

    monkeypatch.setattr(period_scheduler, "run_period_rollover", _run_period_rollover)
    await scheduler.jobs[0][0]()
    assert called
