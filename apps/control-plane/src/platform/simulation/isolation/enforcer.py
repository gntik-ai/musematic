from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.simulation.coordination.runner import SimulationRunner
from platform.simulation.events import SimulationEventPublisher
from platform.simulation.models import SimulationIsolationPolicy, SimulationRun
from platform.simulation.repository import SimulationRepository
from typing import Any


class IsolationEnforcer:
    def __init__(
        self,
        *,
        repository: SimulationRepository,
        policy_service: Any | None,
        runner: SimulationRunner | None,
        publisher: SimulationEventPublisher,
        settings: PlatformSettings,
    ) -> None:
        self.repository = repository
        self.policy_service = policy_service
        self.runner = runner
        self.publisher = publisher
        self.settings = settings

    async def apply(
        self,
        simulation_run: SimulationRun,
        policy: SimulationIsolationPolicy,
    ) -> str | None:
        if self.policy_service is None:
            return None
        register = getattr(self.policy_service, "register_simulation_policy_bundle", None)
        if register is None:
            return None
        rules = translate_policy_rules(policy)
        fingerprint = await register(simulation_run.id, rules, simulation_run.workspace_id)
        await self.repository.set_run_isolation_bundle(
            simulation_run.id,
            simulation_run.workspace_id,
            str(fingerprint),
        )
        simulation_run.isolation_bundle_fingerprint = str(fingerprint)
        return str(fingerprint)

    async def apply_default_strict(self, simulation_run: SimulationRun) -> str | None:
        if not self.settings.simulation.default_strict_isolation:
            return None
        if simulation_run.isolation_policy_id is not None:
            return None
        policy = SimulationIsolationPolicy(
            workspace_id=simulation_run.workspace_id,
            name="Default strict simulation isolation",
            description="Generated strict isolation policy for simulations without explicit policy",
            blocked_actions=[
                {"action_type": "external.write", "severity": "critical"},
                {"action_type": "connector.send_message", "severity": "critical"},
            ],
            stubbed_actions=[
                {"action_type": "connector.*", "stub_response_template": {"status": "stubbed"}}
            ],
            permitted_read_sources=[],
            is_default=True,
            halt_on_critical_breach=True,
        )
        return await self.apply(simulation_run, policy)

    async def release(self, simulation_run: SimulationRun) -> None:
        fingerprint = simulation_run.isolation_bundle_fingerprint
        if self.policy_service is None or not fingerprint:
            return
        deregister = getattr(self.policy_service, "deregister_simulation_policy_bundle", None)
        if deregister is None:
            return
        await deregister(fingerprint)
        await self.repository.set_run_isolation_bundle(
            simulation_run.id,
            simulation_run.workspace_id,
            None,
        )
        simulation_run.isolation_bundle_fingerprint = None

    async def handle_breach(
        self,
        simulation_run: SimulationRun,
        breach_event: dict[str, Any],
    ) -> None:
        await self.publisher.isolation_breach_detected(
            simulation_run.id,
            simulation_run.workspace_id,
            breach_event,
        )
        results = dict(simulation_run.results or {})
        results["isolation_events_count"] = int(results.get("isolation_events_count", 0)) + 1
        simulation_run.results = results
        severity = str(breach_event.get("severity", "")).lower()
        halt = bool(breach_event.get("halt_on_critical_breach", True))
        if severity == "critical" and halt and self.runner is not None:
            await self.runner.cancel(simulation_run.id, simulation_run.workspace_id)


def translate_policy_rules(policy: SimulationIsolationPolicy) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for blocked in policy.blocked_actions or []:
        rules.append(
            {
                "effect": "deny",
                "action_type": blocked.get("action_type"),
                "severity": blocked.get("severity", "critical"),
                "source": "simulation_isolation_policy",
            }
        )
    for stubbed in policy.stubbed_actions or []:
        rules.append(
            {
                "effect": "stub",
                "action_type": stubbed.get("action_type"),
                "stub_response_template": stubbed.get("stub_response_template", {}),
                "source": "simulation_isolation_policy",
            }
        )
    for read_source in policy.permitted_read_sources or []:
        rules.append(
            {
                "effect": "allow_read",
                "source_type": read_source.get("source_type"),
                "source_id": read_source.get("source_id"),
                "source": "simulation_isolation_policy",
            }
        )
    return rules
