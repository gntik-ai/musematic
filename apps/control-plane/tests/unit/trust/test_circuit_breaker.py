from __future__ import annotations

from platform.trust.exceptions import CircuitBreakerTrippedError

import pytest

from tests.trust_support import build_circuit_breaker_config_create, build_trust_bundle

WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_circuit_breaker_trips_publishes_and_pauses_workflow() -> None:
    bundle = build_trust_bundle()
    service = bundle.circuit_breaker_service
    await service.upsert_config(build_circuit_breaker_config_create())

    await service.load_script()
    first = await service.record_failure(
        "agent-1",
        WORKSPACE_ID,
        execution_id="exec-1",
    )
    second = await service.record_failure(
        "agent-1",
        WORKSPACE_ID,
        execution_id="exec-1",
    )

    assert bundle.redis.script_loads
    assert first.tripped is False
    assert second.tripped is True
    assert bundle.runtime_controller.pause_calls[-1]["execution_id"] == "exec-1"
    assert bundle.producer.events[-2]["event_type"] == "circuit_breaker.activated"
    assert bundle.producer.events[-1]["topic"] == "interaction.attention"


@pytest.mark.asyncio
async def test_circuit_breaker_status_reset_and_guard() -> None:
    bundle = build_trust_bundle()
    service = bundle.circuit_breaker_service
    await service.upsert_config(build_circuit_breaker_config_create())
    await service.record_failure("agent-1", WORKSPACE_ID)
    await service.record_failure("agent-1", WORKSPACE_ID)

    status = await service.get_status("agent-1", WORKSPACE_ID)
    configs = await service.list_configs(WORKSPACE_ID)

    assert status.tripped is True
    assert configs.total == 1

    with pytest.raises(CircuitBreakerTrippedError):
        await service.ensure_not_tripped("agent-1")

    await service.reset("agent-1")
    assert await service.is_tripped("agent-1") is False


@pytest.mark.asyncio
async def test_circuit_breaker_evalsha_fallback_and_uuid_helper() -> None:
    class _FallbackRedis(type(build_trust_bundle().redis)):
        async def evalsha(self, sha, numkeys, *args):
            del sha, numkeys, args
            raise RuntimeError("noscript")

    bundle = build_trust_bundle()
    bundle.circuit_breaker_service.redis_client = _FallbackRedis()
    service = bundle.circuit_breaker_service
    await service.upsert_config(build_circuit_breaker_config_create())

    status = await service.record_failure("agent-fallback", WORKSPACE_ID)
    await service.ensure_not_tripped("agent-fallback")

    assert status.failure_count == 1
    assert service._uuid_from_text(WORKSPACE_ID).hex
