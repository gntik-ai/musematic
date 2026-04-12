from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.fleets.events import (
    FleetEventType,
    FleetHealthUpdatedPayload,
    FleetStatusChangedPayload,
    publish_fleet_event,
)
from platform.fleets.exceptions import FleetNotFoundError
from platform.fleets.models import FleetMemberAvailability, FleetStatus
from platform.fleets.repository import FleetMemberRepository, FleetRepository
from platform.fleets.schemas import FleetHealthProjectionResponse, MemberHealthStatus
from platform.interactions.events import AttentionRequestedPayload, publish_attention_requested
from platform.interactions.models import AttentionUrgency
from typing import Any
from uuid import UUID, uuid4


class FleetHealthProjectionService:
    def __init__(
        self,
        *,
        fleet_repo: FleetRepository,
        member_repo: FleetMemberRepository,
        redis_client: Any,
        producer: Any | None,
    ) -> None:
        self.fleet_repo = fleet_repo
        self.member_repo = member_repo
        self.redis_client = redis_client
        self.producer = producer

    async def get_health(self, fleet_id: UUID, workspace_id: UUID) -> FleetHealthProjectionResponse:
        fleet = await self.fleet_repo.get_by_id(fleet_id, workspace_id)
        if fleet is None:
            raise FleetNotFoundError(fleet_id)
        key = f"fleet:health:{fleet_id}"
        cached = await self.redis_client.get(key)
        if cached is not None:
            return FleetHealthProjectionResponse.model_validate_json(cached.decode("utf-8"))
        return await self.refresh_health(fleet_id)

    async def refresh_health(self, fleet_id: UUID) -> FleetHealthProjectionResponse:
        fleet = await self.fleet_repo.get_by_id(fleet_id)
        if fleet is None:
            raise FleetNotFoundError(fleet_id)
        members = await self.member_repo.get_by_fleet(fleet_id)
        client = await self.redis_client._get_client()
        pattern = f"fleet:member:avail:{fleet_id}:*"
        available_fqns: set[str] = set()
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor=cursor, match=pattern, count=100)
            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode("utf-8")
                available_fqns.add(str(key).split(":", 4)[-1])
            if cursor == 0:
                break
        if not available_fqns:
            available_fqns = {
                member.agent_fqn
                for member in members
                if member.availability is FleetMemberAvailability.available
            }
        member_statuses: list[MemberHealthStatus] = []
        available_count = 0
        for member in members:
            availability = (
                FleetMemberAvailability.available
                if member.agent_fqn in available_fqns
                else FleetMemberAvailability.unavailable
            )
            member.availability = availability
            if availability is FleetMemberAvailability.available:
                available_count += 1
            member_statuses.append(
                MemberHealthStatus(
                    agent_fqn=member.agent_fqn,
                    availability=availability,
                    role=member.role,
                )
            )
        total_count = len(member_statuses)
        health_pct = 1.0 if total_count == 0 else available_count / total_count
        required_quorum = min(fleet.quorum_min, total_count) if total_count else 0
        quorum_met = available_count >= required_quorum
        previous_status = fleet.status
        if total_count == 0 or available_count == total_count:
            new_status = FleetStatus.active
        elif quorum_met:
            new_status = FleetStatus.degraded
        else:
            new_status = FleetStatus.paused
        fleet.status = new_status
        projection = FleetHealthProjectionResponse(
            fleet_id=fleet.id,
            status=new_status,
            health_pct=health_pct,
            quorum_met=quorum_met,
            available_count=available_count,
            total_count=total_count,
            member_statuses=member_statuses,
            last_updated=datetime.now(UTC),
        )
        await self.redis_client.set(
            f"fleet:health:{fleet.id}",
            projection.model_dump_json().encode("utf-8"),
            ttl=90,
        )
        correlation = CorrelationContext(
            workspace_id=fleet.workspace_id,
            fleet_id=fleet.id,
            correlation_id=uuid4(),
        )
        if previous_status is not new_status:
            await publish_fleet_event(
                self.producer,
                FleetEventType.fleet_status_changed,
                FleetStatusChangedPayload(
                    fleet_id=fleet.id,
                    workspace_id=fleet.workspace_id,
                    status=new_status.value,
                    previous_status=previous_status.value if previous_status else None,
                    reason="quorum_recomputed",
                ),
                correlation,
            )
            if new_status is FleetStatus.paused:
                await publish_attention_requested(
                    self.producer,
                    AttentionRequestedPayload(
                        request_id=uuid4(),
                        workspace_id=fleet.workspace_id,
                        source_agent_fqn="platform:fleet-health-monitor",
                        target_identity="platform_admin",
                        urgency=AttentionUrgency.high,
                        related_interaction_id=None,
                        related_goal_id=None,
                    ),
                    correlation,
                )
        await publish_fleet_event(
            self.producer,
            FleetEventType.fleet_health_updated,
            FleetHealthUpdatedPayload(
                fleet_id=fleet.id,
                workspace_id=fleet.workspace_id,
                health_pct=projection.health_pct,
                quorum_met=projection.quorum_met,
                status=projection.status.value,
                available_count=projection.available_count,
                total_count=projection.total_count,
                member_statuses=[
                    item.model_dump(mode="json") for item in projection.member_statuses
                ],
            ),
            correlation,
        )
        return projection

    async def handle_member_availability_change(
        self, agent_fqn: str, *, is_available: bool
    ) -> None:
        memberships = await self.member_repo.get_by_agent_fqn_across_fleets(agent_fqn)
        if not memberships:
            return
        client = await self.redis_client._get_client()
        for membership in memberships:
            membership.availability = (
                FleetMemberAvailability.available
                if is_available
                else FleetMemberAvailability.unavailable
            )
            key = f"fleet:member:avail:{membership.fleet_id}:{membership.agent_fqn}"
            if is_available:
                await client.set(key, "1", ex=120)
            else:
                await client.delete(key)
            await self.refresh_health(membership.fleet_id)
