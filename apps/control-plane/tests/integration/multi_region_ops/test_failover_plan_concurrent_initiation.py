from __future__ import annotations

import asyncio
from platform.multi_region_ops.exceptions import FailoverInProgressError
from platform.multi_region_ops.services.failover_service import FailoverService
from platform.multi_region_ops.services.failover_steps.base import StepOutcome
from typing import Any

import pytest

from tests.integration.multi_region_ops.support import (
    build_services,
    create_failover_plan_request,
    seeded_repository,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class SlowStepAdapter:
    kind = "custom"

    async def execute(self, **kwargs: Any) -> StepOutcome:
        await asyncio.sleep(0.05)
        return StepOutcome(
            kind="custom",
            name=str(kwargs["parameters"]["name"]),
            outcome="succeeded",
        )


class LockingFailoverService(FailoverService):
    locked = False

    async def acquire_failover_lock(self, from_region: str, to_region: str) -> str | None:
        del from_region, to_region
        if LockingFailoverService.locked:
            return None
        LockingFailoverService.locked = True
        return "shared-lock"

    async def release_failover_lock(self, from_region: str, to_region: str, token: str) -> bool:
        del from_region, to_region, token
        LockingFailoverService.locked = False
        return True


async def test_concurrent_rehearsal_allows_one_initiator() -> None:
    LockingFailoverService.locked = False
    repository = seeded_repository()
    services = build_services(repository)
    base = services["failover"]
    service = LockingFailoverService(
        repository=repository,  # type: ignore[arg-type]
        settings=services["settings"],
        step_adapters={"custom": SlowStepAdapter()},  # type: ignore[arg-type]
    )
    plan = await base.create_plan(create_failover_plan_request(1))

    results = await asyncio.gather(
        service.rehearse(plan.id),
        service.rehearse(plan.id),
        return_exceptions=True,
    )

    successes = [item for item in results if not isinstance(item, Exception)]
    failures = [item for item in results if isinstance(item, FailoverInProgressError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].details["running_run_id"] is not None
