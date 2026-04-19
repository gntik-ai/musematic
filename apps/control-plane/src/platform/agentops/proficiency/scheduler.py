from __future__ import annotations

from platform.agentops.events import AgentOpsEventType, GovernanceEventPublisher
from platform.agentops.proficiency.service import ProficiencyService
from typing import Any
from uuid import UUID


class ProficiencyRecomputerTask:
    def __init__(
        self,
        *,
        proficiency_service: ProficiencyService,
        registry_service: Any,
        governance_publisher: GovernanceEventPublisher | None,
    ) -> None:
        self.proficiency_service = proficiency_service
        self.registry_service = registry_service
        self.governance_publisher = governance_publisher

    async def run(self, workspace_id: UUID | None = None) -> list[dict[str, object]]:
        if self.registry_service is None or not hasattr(
            self.registry_service, "list_active_agents"
        ):
            return []
        items: list[dict[str, object]] = []
        for target in await self.registry_service.list_active_agents(workspace_id):
            agent_fqn = str(target.get("agent_fqn"))
            resolved_workspace_id = UUID(str(target.get("workspace_id")))
            previous = await self.proficiency_service.repository.get_latest_proficiency_assessment(
                agent_fqn, resolved_workspace_id
            )
            response = await self.proficiency_service.compute_for_agent(
                agent_fqn,
                resolved_workspace_id,
                trigger="scheduled",
            )
            items.append(
                {
                    "agent_fqn": agent_fqn,
                    "workspace_id": resolved_workspace_id,
                    "level": response.level,
                }
            )
            if self.governance_publisher is not None:
                await self.governance_publisher.record(
                    AgentOpsEventType.proficiency_assessed.value,
                    agent_fqn,
                    resolved_workspace_id,
                    payload={
                        "level": str(response.level),
                        "previous_level": str(previous.level) if previous is not None else None,
                    },
                    actor=None,
                    revision_id=None,
                )
        return items
