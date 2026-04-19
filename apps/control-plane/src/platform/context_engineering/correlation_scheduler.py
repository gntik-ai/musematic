from __future__ import annotations

from platform.context_engineering.correlation_service import CorrelationService
from typing import Any
from uuid import UUID


class CorrelationRecomputerTask:
    def __init__(
        self,
        *,
        correlation_service: CorrelationService,
        registry_service: Any,
        default_window_days: int,
    ) -> None:
        self.correlation_service = correlation_service
        self.registry_service = registry_service
        self.default_window_days = default_window_days

    async def run(self, workspace_id: UUID | None = None) -> list[dict[str, object]]:
        if self.registry_service is None or not hasattr(
            self.registry_service,
            "list_active_agents",
        ):
            return []
        items: list[dict[str, object]] = []
        for target in await self.registry_service.list_active_agents(workspace_id):
            agent_fqn = str(target.get("agent_fqn"))
            resolved_workspace_id = UUID(str(target.get("workspace_id")))
            results = await self.correlation_service.compute_for_agent(
                resolved_workspace_id,
                agent_fqn,
                window_days=self.default_window_days,
            )
            items.append(
                {
                    "agent_fqn": agent_fqn,
                    "workspace_id": resolved_workspace_id,
                    "count": len(results),
                }
            )
        return items

    async def enqueue_recompute(
        self,
        workspace_id: UUID,
        *,
        agent_fqn: str | None = None,
        window_days: int | None = None,
    ) -> list[dict[str, object]]:
        if agent_fqn is not None:
            results = await self.correlation_service.compute_for_agent(
                workspace_id,
                agent_fqn,
                window_days=window_days or self.default_window_days,
            )
            return [
                {
                    "agent_fqn": agent_fqn,
                    "workspace_id": workspace_id,
                    "count": len(results),
                }
            ]
        return await self.run(workspace_id)
