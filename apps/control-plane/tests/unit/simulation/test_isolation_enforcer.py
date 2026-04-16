from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.simulation.isolation.enforcer import IsolationEnforcer, translate_policy_rules
from platform.simulation.models import SimulationIsolationPolicy, SimulationRun
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


class FakeRepository:
    def __init__(self) -> None:
        self.bundle: str | None = None

    async def set_run_isolation_bundle(self, run_id, workspace_id, bundle_fingerprint):
        self.bundle = bundle_fingerprint
        return None


class FakePublisher:
    def __init__(self) -> None:
        self.breaches: list[object] = []

    async def isolation_breach_detected(self, run_id, workspace_id, breach_event):
        self.breaches.append((run_id, workspace_id, breach_event))


def _run() -> SimulationRun:
    run = SimulationRun(
        workspace_id=uuid4(),
        name="scenario",
        digital_twin_ids=[],
        scenario_config={},
        status="running",
        initiated_by=uuid4(),
    )
    run.id = uuid4()
    run.created_at = datetime.now(UTC)
    return run


def _policy(workspace_id) -> SimulationIsolationPolicy:
    policy = SimulationIsolationPolicy(
        workspace_id=workspace_id,
        name="strict",
        blocked_actions=[{"action_type": "connector.send_message", "severity": "critical"}],
        stubbed_actions=[{"action_type": "connector.read_data", "stub_response_template": {}}],
        permitted_read_sources=[{"source_type": "dataset", "source_id": "ds-1"}],
        is_default=False,
        halt_on_critical_breach=True,
    )
    policy.id = uuid4()
    return policy


@pytest.mark.asyncio
async def test_apply_and_release_registers_policy_bundle() -> None:
    run = _run()
    policy_service = SimpleNamespace(
        register_simulation_policy_bundle=AsyncMock(return_value="fp"),
        deregister_simulation_policy_bundle=AsyncMock(),
    )
    enforcer = IsolationEnforcer(
        repository=FakeRepository(),
        policy_service=policy_service,
        runner=None,
        publisher=FakePublisher(),
        settings=PlatformSettings(),
    )

    fingerprint = await enforcer.apply(run, _policy(run.workspace_id))
    await enforcer.release(run)

    assert fingerprint == "fp"
    args = policy_service.register_simulation_policy_bundle.await_args.args
    assert args[0] == run.id
    assert {item["effect"] for item in args[1]} == {"deny", "stub", "allow_read"}
    policy_service.deregister_simulation_policy_bundle.assert_awaited_once_with("fp")


@pytest.mark.asyncio
async def test_handle_breach_cancels_only_critical_breaches() -> None:
    run = _run()
    runner = SimpleNamespace(cancel=AsyncMock())
    publisher = FakePublisher()
    enforcer = IsolationEnforcer(
        repository=FakeRepository(),
        policy_service=None,
        runner=runner,
        publisher=publisher,
        settings=PlatformSettings(),
    )

    await enforcer.handle_breach(run, {"severity": "warning"})
    runner.cancel.assert_not_awaited()
    await enforcer.handle_breach(run, {"severity": "critical"})

    runner.cancel.assert_awaited_once_with(run.id, run.workspace_id)
    assert run.results["isolation_events_count"] == 2
    assert len(publisher.breaches) == 2


@pytest.mark.asyncio
async def test_default_strict_policy_is_applied_when_enabled() -> None:
    run = _run()
    policy_service = SimpleNamespace(
        register_simulation_policy_bundle=AsyncMock(return_value="strict-fp")
    )
    enforcer = IsolationEnforcer(
        repository=FakeRepository(),
        policy_service=policy_service,
        runner=None,
        publisher=FakePublisher(),
        settings=PlatformSettings(),
    )

    fingerprint = await enforcer.apply_default_strict(run)

    assert fingerprint == "strict-fp"
    rules = policy_service.register_simulation_policy_bundle.await_args.args[1]
    assert any(rule["action_type"] == "external.write" for rule in rules)


def test_translate_policy_rules_preserves_policy_semantics() -> None:
    run = _run()
    rules = translate_policy_rules(_policy(run.workspace_id))
    assert rules[0]["effect"] == "deny"
    assert rules[1]["effect"] == "stub"
    assert rules[2]["effect"] == "allow_read"
