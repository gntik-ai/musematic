from __future__ import annotations

from platform.a2a_gateway.schemas import (
    AgentCardAuthentication,
    AgentCardResponse,
    AgentCardSkill,
)
from platform.registry.models import AgentProfile, LifecycleStatus
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class AgentCardGenerator:
    def __init__(self, *, base_path: str = "/api/v1/a2a") -> None:
        self.base_path = base_path

    async def generate_platform_card(
        self,
        session: AsyncSession,
        *,
        base_url: str = "https://platform.example.com",
    ) -> dict[str, Any]:
        result = await session.execute(
            select(AgentProfile)
            .options(
                selectinload(AgentProfile.revisions),
                selectinload(AgentProfile.namespace),
            )
            .where(
                AgentProfile.status == LifecycleStatus.published,
                AgentProfile.deleted_at.is_(None),
            )
            .order_by(AgentProfile.fqn.asc())
        )
        profiles = list(result.scalars().all())
        skills: list[AgentCardSkill] = []
        aggregated_capabilities: set[str] = {"streaming", "multi-turn"}
        for profile in profiles:
            if not profile.revisions:
                continue
            manifest = profile.revisions[-1].manifest_snapshot
            reasoning_modes = manifest.get("reasoning_modes", [])
            skill_capabilities: list[str] = []
            if isinstance(reasoning_modes, list):
                skill_capabilities = [
                    str(item) for item in reasoning_modes if isinstance(item, str)
                ]
            aggregated_capabilities.update(skill_capabilities)
            skills.append(
                AgentCardSkill(
                    id=profile.fqn,
                    name=profile.fqn,
                    description=profile.purpose,
                    tags=list(profile.tags),
                    capabilities=skill_capabilities,
                )
            )

        card = AgentCardResponse(
            name="Agentic Mesh Platform",
            description=(
                "Multi-tenant agent orchestration platform exposing platform agents via A2A."
            ),
            url=f"{base_url.rstrip('/')}{self.base_path}",
            version="1.0",
            capabilities=sorted(aggregated_capabilities),
            authentication=[
                AgentCardAuthentication(
                    scheme="bearer",
                    **{"in": "header"},
                    name="Authorization",
                )
            ],
            skills=skills,
        )
        return card.model_dump(mode="json", by_alias=True)
