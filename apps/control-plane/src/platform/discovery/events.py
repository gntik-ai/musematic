from __future__ import annotations

from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from typing import Any, Final
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict


class DiscoveryEventType(StrEnum):
    session_started = "session_started"
    hypothesis_generated = "hypothesis_generated"
    critique_completed = "critique_completed"
    tournament_round_completed = "tournament_round_completed"
    cycle_completed = "cycle_completed"
    session_converged = "session_converged"
    session_halted = "session_halted"
    experiment_designed = "experiment_designed"
    experiment_completed = "experiment_completed"
    proximity_computed = "proximity_computed"


class DiscoveryEventPayload(BaseModel):
    """Common payload schema for discovery events."""

    model_config = ConfigDict(extra="allow")

    session_id: UUID
    workspace_id: UUID
    actor_id: UUID | None = None


DISCOVERY_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    event_type.value: DiscoveryEventPayload for event_type in DiscoveryEventType
}


def register_discovery_event_types() -> None:
    """Register discovery event schemas with the platform event registry."""
    for event_type, schema in DISCOVERY_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


class DiscoveryEventPublisher:
    """Publish discovery lifecycle events to Kafka."""

    def __init__(self, producer: EventProducer | None) -> None:
        self.producer = producer

    async def publish(
        self,
        event_type: DiscoveryEventType | str,
        *,
        session_id: UUID,
        workspace_id: UUID,
        payload: dict[str, Any] | None = None,
        actor_id: UUID | None = None,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        if self.producer is None:
            return
        enriched = {
            "session_id": session_id,
            "workspace_id": workspace_id,
            "actor_id": actor_id,
            **(payload or {}),
        }
        await self.producer.publish(
            topic="discovery.events",
            key=str(session_id),
            event_type=str(
                event_type.value if isinstance(event_type, DiscoveryEventType) else event_type
            ),
            payload=enriched,
            correlation_ctx=correlation_ctx
            or CorrelationContext(workspace_id=workspace_id, correlation_id=uuid4()),
            source="platform.discovery",
        )

    async def session_started(
        self,
        session_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
    ) -> None:
        await self.publish(
            DiscoveryEventType.session_started,
            session_id=session_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
        )

    async def hypothesis_generated(
        self,
        session_id: UUID,
        workspace_id: UUID,
        hypothesis_id: UUID,
    ) -> None:
        await self.publish(
            DiscoveryEventType.hypothesis_generated,
            session_id=session_id,
            workspace_id=workspace_id,
            payload={"hypothesis_id": str(hypothesis_id)},
        )

    async def critique_completed(
        self,
        session_id: UUID,
        workspace_id: UUID,
        hypothesis_id: UUID,
    ) -> None:
        await self.publish(
            DiscoveryEventType.critique_completed,
            session_id=session_id,
            workspace_id=workspace_id,
            payload={"hypothesis_id": str(hypothesis_id)},
        )

    async def tournament_round_completed(
        self,
        session_id: UUID,
        workspace_id: UUID,
        round_id: UUID,
    ) -> None:
        await self.publish(
            DiscoveryEventType.tournament_round_completed,
            session_id=session_id,
            workspace_id=workspace_id,
            payload={"round_id": str(round_id)},
        )

    async def cycle_completed(
        self,
        session_id: UUID,
        workspace_id: UUID,
        cycle_id: UUID,
        converged: bool,
    ) -> None:
        await self.publish(
            DiscoveryEventType.cycle_completed,
            session_id=session_id,
            workspace_id=workspace_id,
            payload={"cycle_id": str(cycle_id), "converged": converged},
        )

    async def session_converged(
        self,
        session_id: UUID,
        workspace_id: UUID,
        cycle_id: UUID,
    ) -> None:
        await self.publish(
            DiscoveryEventType.session_converged,
            session_id=session_id,
            workspace_id=workspace_id,
            payload={"cycle_id": str(cycle_id)},
        )

    async def session_halted(
        self,
        session_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
        reason: str,
    ) -> None:
        await self.publish(
            DiscoveryEventType.session_halted,
            session_id=session_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            payload={"reason": reason},
        )

    async def experiment_designed(
        self,
        session_id: UUID,
        workspace_id: UUID,
        experiment_id: UUID,
    ) -> None:
        await self.publish(
            DiscoveryEventType.experiment_designed,
            session_id=session_id,
            workspace_id=workspace_id,
            payload={"experiment_id": str(experiment_id)},
        )

    async def experiment_completed(
        self,
        session_id: UUID,
        workspace_id: UUID,
        experiment_id: UUID,
    ) -> None:
        await self.publish(
            DiscoveryEventType.experiment_completed,
            session_id=session_id,
            workspace_id=workspace_id,
            payload={"experiment_id": str(experiment_id)},
        )

    async def proximity_computed(
        self,
        session_id: UUID,
        workspace_id: UUID,
        cluster_count: int,
    ) -> None:
        await self.publish(
            DiscoveryEventType.proximity_computed,
            session_id=session_id,
            workspace_id=workspace_id,
            payload={"cluster_count": cluster_count},
        )
