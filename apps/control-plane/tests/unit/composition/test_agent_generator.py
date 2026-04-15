from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.composition.generators.agent import AgentBlueprintGenerator, build_agent_system_prompt
from platform.composition.schemas import AgentBlueprintRaw, WorkspaceCompositionContext
from uuid import uuid4

import pytest


class FakeLLM:
    def __init__(self, raw: AgentBlueprintRaw) -> None:
        self.raw = raw
        self.calls: list[tuple[str, str, type[AgentBlueprintRaw]]] = []

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[AgentBlueprintRaw],
    ) -> AgentBlueprintRaw:
        self.calls.append((system_prompt, user_prompt, response_schema))
        return self.raw


def _raw(confidence: float = 0.9) -> AgentBlueprintRaw:
    return AgentBlueprintRaw.model_validate(
        {
            "model_config": {"model_id": "gpt-test", "temperature": 0.2, "max_tokens": 1000},
            "tool_selections": [{"tool_name": "browser", "relevance_justification": "research"}],
            "connector_suggestions": [{"connector_type": "web", "connector_name": "webhook"}],
            "policy_recommendations": [{"policy_name": "safe-output"}],
            "context_profile": {"assembly_strategy": "standard", "memory_scope": "workspace"},
            "maturity_estimate": "developing",
            "maturity_reasoning": "enough context",
            "confidence_score": confidence,
            "follow_up_questions": [{"question": "What sources?", "context": "research"}],
            "llm_reasoning_summary": "summary",
            "alternatives_considered": [],
        }
    )


@pytest.mark.asyncio
async def test_agent_generator_passes_context_without_secrets() -> None:
    workspace_id = uuid4()
    raw = _raw()
    llm = FakeLLM(raw)
    generator = AgentBlueprintGenerator(llm, PlatformSettings())
    context = WorkspaceCompositionContext(
        available_tools=[
            {"name": "browser", "capability_description": "browse", "api_key": "super-secret"}
        ],
        available_models=[{"identifier": "gpt-test", "provider": "local", "tier": "dev"}],
    )

    result = await generator.generate("research agent", workspace_id, context)

    assert result is raw
    system_prompt, user_prompt, schema = llm.calls[0]
    assert schema is AgentBlueprintRaw
    assert "research agent" in user_prompt
    assert str(workspace_id) in user_prompt
    assert "browser" in system_prompt
    assert "api_key" not in system_prompt
    assert "super-secret" not in system_prompt
    assert "Do not include secrets" in system_prompt


def test_build_agent_system_prompt_includes_required_sections() -> None:
    prompt = build_agent_system_prompt(WorkspaceCompositionContext())

    assert "model_config" in prompt
    assert "tool_selections" in prompt
    assert "policy_recommendations" in prompt
