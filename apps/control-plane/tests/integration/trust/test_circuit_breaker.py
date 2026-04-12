from __future__ import annotations

from platform.trust.router import (
    get_circuit_breaker_status,
    reset_circuit_breaker,
    upsert_circuit_breaker_config,
)
from platform.trust.schemas import CircuitBreakerConfigCreate

import pytest

from tests.trust_support import admin_user, build_trust_bundle

WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_circuit_breaker_endpoints() -> None:
    bundle = build_trust_bundle()

    created = await upsert_circuit_breaker_config(
        CircuitBreakerConfigCreate(
            workspace_id=WORKSPACE_ID,
            agent_id="agent-1",
            failure_threshold=2,
            time_window_seconds=600,
            tripped_ttl_seconds=3600,
            enabled=True,
        ),
        current_user=admin_user(),
        circuit_breaker_service=bundle.circuit_breaker_service,
    )
    await bundle.circuit_breaker_service.record_failure("agent-1", WORKSPACE_ID)
    await bundle.circuit_breaker_service.record_failure("agent-1", WORKSPACE_ID)
    status = await get_circuit_breaker_status(
        "agent-1",
        workspace_id=WORKSPACE_ID,
        fleet_id=None,
        current_user=admin_user(),
        circuit_breaker_service=bundle.circuit_breaker_service,
    )
    reset = await reset_circuit_breaker(
        "agent-1",
        current_user=admin_user(),
        circuit_breaker_service=bundle.circuit_breaker_service,
    )

    assert created.agent_id == "agent-1"
    assert status.tripped is True
    assert reset.status_code == 204
