from __future__ import annotations

import json
from platform.common.config import PlatformSettings
from platform.composition.llm.client import LLMCompositionClient
from platform.composition.schemas import AgentBlueprintRaw, WorkspaceCompositionContext
from uuid import UUID


class AgentBlueprintGenerator:
    """Generate agent blueprint payloads from natural-language descriptions."""

    def __init__(
        self,
        llm_client: LLMCompositionClient,
        settings: PlatformSettings,
    ) -> None:
        self.llm_client = llm_client
        self.settings = settings

    async def generate(
        self,
        description: str,
        workspace_id: UUID,
        workspace_context: WorkspaceCompositionContext,
    ) -> AgentBlueprintRaw:
        """Generate a structured agent blueprint from a description."""
        system_prompt = build_agent_system_prompt(workspace_context)
        user_prompt = (
            "Generate a complete agent blueprint for this workspace.\n"
            f"workspace_id: {workspace_id}\n"
            f"description: {description}"
        )
        return await self.llm_client.generate(system_prompt, user_prompt, AgentBlueprintRaw)


def build_agent_system_prompt(workspace_context: WorkspaceCompositionContext) -> str:
    """Build a secret-free system prompt for agent blueprint generation."""
    safe_context = _safe_context(workspace_context)
    return (
        "You generate JSON-only Musematic agent blueprints. "
        "Return model_config, tool_selections, connector_suggestions, "
        "policy_recommendations, context_profile, maturity_estimate, maturity_reasoning, "
        "confidence_score, follow_up_questions, llm_reasoning_summary, and "
        "alternatives_considered. Do not include secrets, credentials, API keys, or "
        "connection strings. Use only this platform context:\n"
        f"{json.dumps(safe_context, sort_keys=True)}"
    )


def _safe_context(workspace_context: WorkspaceCompositionContext) -> dict[str, object]:
    return {
        "available_tools": [
            {
                key: item[key]
                for key in ("name", "capability_description", "tool_type")
                if key in item
            }
            for item in workspace_context.available_tools
        ],
        "available_models": [
            {key: item[key] for key in ("identifier", "provider", "tier") if key in item}
            for item in workspace_context.available_models
        ],
        "available_connectors": [
            {
                key: item[key]
                for key in ("connector_name", "connector_type", "status")
                if key in item
            }
            for item in workspace_context.available_connectors
        ],
        "active_policies": [
            {key: item[key] for key in ("name", "description", "scope") if key in item}
            for item in workspace_context.active_policies
        ],
        "context_engineering_strategies": workspace_context.context_engineering_strategies,
    }
