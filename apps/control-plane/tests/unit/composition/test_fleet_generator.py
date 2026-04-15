from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.composition.generators.fleet import FleetBlueprintGenerator, build_fleet_system_prompt
from platform.composition.schemas import FleetBlueprintRaw, WorkspaceCompositionContext
from uuid import uuid4

import pytest


class FakeLLM:
    def __init__(self, raw: FleetBlueprintRaw) -> None:
        self.raw = raw
        self.calls: list[tuple[str, str, type[FleetBlueprintRaw]]] = []

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[FleetBlueprintRaw],
    ) -> FleetBlueprintRaw:
        self.calls.append((system_prompt, user_prompt, response_schema))
        return self.raw


def _raw(member_count: int = 3, confidence: float = 0.8) -> FleetBlueprintRaw:
    roles = [
        {"role_name": f"role-{index}", "purpose": "work", "agent_blueprint_inline": {}}
        for index in range(member_count)
    ]
    return FleetBlueprintRaw.model_validate(
        {
            "topology_type": "sequential",
            "member_roles": roles,
            "orchestration_rules": [{"rule_type": "routing", "action": "send"}],
            "delegation_rules": [{"from_role": "role-0", "to_role": "role-1"}],
            "escalation_rules": [{"from_role": "role-1", "to_role": "role-2", "urgency": "high"}],
            "confidence_score": confidence,
        }
    )


@pytest.mark.asyncio
async def test_fleet_generator_sets_single_agent_suggestion_for_single_role() -> None:
    raw = _raw(member_count=1)
    llm = FakeLLM(raw)
    generator = FleetBlueprintGenerator(llm, PlatformSettings())

    result = await generator.generate("single role mission", uuid4(), WorkspaceCompositionContext())

    assert result.single_agent_suggestion is True
    assert llm.calls[0][2] is FleetBlueprintRaw
    assert "fleet blueprint" in llm.calls[0][0]


@pytest.mark.asyncio
async def test_fleet_generator_keeps_multi_role_topology() -> None:
    raw = _raw(member_count=3)
    generator = FleetBlueprintGenerator(FakeLLM(raw), PlatformSettings())

    result = await generator.generate("pipeline team", uuid4(), WorkspaceCompositionContext())

    assert result.single_agent_suggestion is False
    assert len(result.member_roles) == 3


def test_build_fleet_system_prompt_mentions_delegation_and_secrets() -> None:
    prompt = build_fleet_system_prompt(WorkspaceCompositionContext())

    assert "delegation_rules" in prompt
    assert "escalation_rules" in prompt
    assert "Do not include secrets" in prompt
