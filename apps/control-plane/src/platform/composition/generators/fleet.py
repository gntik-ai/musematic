from __future__ import annotations

import json
from platform.common.config import PlatformSettings
from platform.composition.generators.agent import _safe_context
from platform.composition.llm.client import LLMCompositionClient
from platform.composition.schemas import FleetBlueprintRaw, WorkspaceCompositionContext
from uuid import UUID


class FleetBlueprintGenerator:
    """Generate fleet blueprint payloads from mission descriptions."""

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
    ) -> FleetBlueprintRaw:
        """Generate a structured fleet blueprint from a mission description."""
        system_prompt = build_fleet_system_prompt(workspace_context)
        user_prompt = (
            "Generate a complete fleet blueprint for this workspace.\n"
            f"workspace_id: {workspace_id}\n"
            f"mission: {description}"
        )
        raw = await self.llm_client.generate(system_prompt, user_prompt, FleetBlueprintRaw)
        if len(raw.member_roles) <= 1:
            raw.single_agent_suggestion = True
        return raw


def build_fleet_system_prompt(workspace_context: WorkspaceCompositionContext) -> str:
    """Build a secret-free system prompt for fleet blueprint generation."""
    safe_context = _safe_context(workspace_context)
    return (
        "You generate JSON-only Musematic fleet blueprints. Return topology_type, "
        "member_roles, orchestration_rules, delegation_rules, escalation_rules, "
        "confidence_score, follow_up_questions, llm_reasoning_summary, "
        "alternatives_considered, and single_agent_suggestion. Member roles should include "
        "inline agent blueprint structures. Do not include secrets, credentials, API keys, "
        "or connection strings. Use only this platform context:\n"
        f"{json.dumps(safe_context, sort_keys=True)}"
    )
