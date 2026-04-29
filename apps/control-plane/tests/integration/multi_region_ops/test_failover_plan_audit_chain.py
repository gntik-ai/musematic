from __future__ import annotations

from platform.multi_region_ops.schemas import FailoverPlanUpdateRequest

import pytest

from tests.integration.multi_region_ops.support import (
    RecordingAudit,
    build_services,
    create_failover_plan_request,
    seeded_repository,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_failover_plan_mutations_and_runs_emit_audit_entries() -> None:
    repository = seeded_repository()
    audit = RecordingAudit()
    services = build_services(repository, audit=audit)
    plan = await services["failover"].create_plan(create_failover_plan_request(1))
    await services["failover"].update_plan(
        plan.id,
        FailoverPlanUpdateRequest(expected_version=1, name="primary-to-dr-updated"),
    )
    rehearsal = await services["failover"].rehearse(plan.id)
    await services["failover"].execute(plan.id, reason="incident")
    await services["failover"].delete_plan(plan.id)

    sources = [entry[1] for entry in audit.entries]
    assert sources == [
        "multi_region_ops.failover_plan.created",
        "multi_region_ops.failover_plan.updated",
        "multi_region_ops.failover_plan.run",
        "multi_region_ops.failover_plan.run",
        "multi_region_ops.failover_plan.deleted",
    ]
    assert str(rehearsal.id) in audit.entries[2][2].decode()


async def test_failover_plan_mutation_fails_when_audit_write_fails() -> None:
    services = build_services(seeded_repository(), audit=RecordingAudit(fail=True))

    with pytest.raises(RuntimeError, match="audit chain unavailable"):
        await services["failover"].create_plan(create_failover_plan_request(1))
