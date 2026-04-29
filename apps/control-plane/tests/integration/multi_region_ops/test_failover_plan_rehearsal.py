from __future__ import annotations

import pytest

from tests.integration.multi_region_ops.support import (
    RecordingStepAdapter,
    build_services,
    create_failover_plan_request,
    seeded_repository,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_failover_rehearsal_records_steps_and_halts_after_failure() -> None:
    repository = seeded_repository()
    services = build_services(repository, step_adapter=RecordingStepAdapter())
    successful = await services["failover"].create_plan(create_failover_plan_request(5))
    successful_run = await services["failover"].rehearse(successful.id, reason="quarterly")

    assert successful_run.outcome == "succeeded"
    assert len(successful_run.step_outcomes) == 5
    assert all(item["duration_ms"] >= 0 for item in successful_run.step_outcomes)
    assert repository.plans[successful.id].tested_at is not None

    failing_services = build_services(repository, step_adapter=RecordingStepAdapter(fail_on_call=3))
    failing = await failing_services["failover"].create_plan(create_failover_plan_request(5))
    failed_run = await failing_services["failover"].rehearse(failing.id, reason="break step 3")

    assert failed_run.outcome == "failed"
    assert [item["outcome"] for item in failed_run.step_outcomes] == [
        "succeeded",
        "succeeded",
        "failed",
        "aborted",
        "aborted",
    ]
    assert repository.plans[failing.id].last_executed_at is None
