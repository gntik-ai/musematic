from __future__ import annotations

from platform.fleet_learning.models import AutonomyLevel, FleetPersonalityProfile
from platform.fleet_learning.repository import FleetPersonalityProfileRepository
from platform.fleet_learning.schemas import (
    FleetPersonalityProfileCreate,
    FleetPersonalityProfileResponse,
    default_personality_profile,
)
from platform.fleets.schemas import OrchestrationModifier
from uuid import UUID


class FleetPersonalityProfileService:
    def __init__(self, *, repository: FleetPersonalityProfileRepository) -> None:
        self.repository = repository

    async def get(self, fleet_id: UUID, workspace_id: UUID) -> FleetPersonalityProfileResponse:
        current = await self.repository.get_current(fleet_id)
        if current is None or current.workspace_id != workspace_id:
            return default_personality_profile(fleet_id)
        return FleetPersonalityProfileResponse.model_validate(current)

    async def update(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
        request: FleetPersonalityProfileCreate,
    ) -> FleetPersonalityProfileResponse:
        current = await self.repository.get_current(fleet_id)
        version_number = 1 if current is None else current.version + 1
        created = await self.repository.create_version(
            FleetPersonalityProfile(
                fleet_id=fleet_id,
                workspace_id=workspace_id,
                communication_style=request.communication_style,
                decision_speed=request.decision_speed,
                risk_tolerance=request.risk_tolerance,
                autonomy_level=request.autonomy_level,
                version=version_number,
                is_current=True,
            )
        )
        return FleetPersonalityProfileResponse.model_validate(created)

    async def get_modifier(self, fleet_id: UUID) -> OrchestrationModifier:
        current = await self.repository.get_current(fleet_id)
        profile = (
            FleetPersonalityProfileResponse.model_validate(current)
            if current is not None
            else default_personality_profile(fleet_id)
        )
        modifier = OrchestrationModifier()
        if profile.decision_speed.value == "fast":
            modifier.max_wait_ms = 0
        elif profile.decision_speed.value == "deliberate":
            modifier.max_wait_ms = 5000
        if profile.decision_speed.value == "consensus_seeking":
            modifier.require_quorum_for_decision = True
        if profile.risk_tolerance.value == "conservative":
            modifier.escalate_unverified = True
        if profile.autonomy_level == AutonomyLevel.fully_autonomous:
            modifier.auto_approve = True
        return modifier
