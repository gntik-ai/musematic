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
    cluster_saturated = "cluster_saturated"
    gap_filled = "gap_filled"


class DiscoveryEventPayload(BaseModel):
    """Common payload schema for discovery events."""

    model_config = ConfigDict(extra="allow")

    session_id: UUID | None = None
    workspace_id: UUID
    actor_id: UUID | None = None


class ClusterSaturatedPayload(DiscoveryEventPayload):
    cluster_id: str
    classification_from: str
    classification_to: str
    member_count: int
    density: float


class GapFilledPayload(DiscoveryEventPayload):
    former_gap_label: str
    now_part_of_cluster_id: str | None = None


DISCOVERY_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    DiscoveryEventType.session_started.value: DiscoveryEventPayload,
    DiscoveryEventType.hypothesis_generated.value: DiscoveryEventPayload,
    DiscoveryEventType.critique_completed.value: DiscoveryEventPayload,
    DiscoveryEventType.tournament_round_completed.value: DiscoveryEventPayload,
    DiscoveryEventType.cycle_completed.value: DiscoveryEventPayload,
    DiscoveryEventType.session_converged.value: DiscoveryEventPayload,
    DiscoveryEventType.session_halted.value: DiscoveryEventPayload,
    DiscoveryEventType.experiment_designed.value: DiscoveryEventPayload,
    DiscoveryEventType.experiment_completed.value: DiscoveryEventPayload,
    DiscoveryEventType.proximity_computed.value: DiscoveryEventPayload,
    DiscoveryEventType.cluster_saturated.value: ClusterSaturatedPayload,
    DiscoveryEventType.gap_filled.value: GapFilledPayload,
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
        session_id: UUID | None,
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
            key=str(session_id or workspace_id),
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
        session_id: UUID | None,
        workspace_id: UUID,
        cluster_count: int,
    ) -> None:
        await self.publish(
            DiscoveryEventType.proximity_computed,
            session_id=session_id,
            workspace_id=workspace_id,
            payload={"cluster_count": cluster_count},
        )

    async def cluster_saturated(
        self,
        *,
        workspace_id: UUID,
        cluster_id: str,
        classification_from: str,
        classification_to: str,
        member_count: int,
        density: float,
        session_id: UUID | None = None,
    ) -> None:
        await self.publish(
            DiscoveryEventType.cluster_saturated,
            session_id=session_id,
            workspace_id=workspace_id,
            payload={
                "cluster_id": cluster_id,
                "classification_from": classification_from,
                "classification_to": classification_to,
                "member_count": member_count,
                "density": density,
            },
        )

    async def gap_filled(
        self,
        *,
        workspace_id: UUID,
        former_gap_label: str,
        now_part_of_cluster_id: str | None,
        session_id: UUID | None = None,
    ) -> None:
        await self.publish(
            DiscoveryEventType.gap_filled,
            session_id=session_id,
            workspace_id=workspace_id,
            payload={
                "former_gap_label": former_gap_label,
                "now_part_of_cluster_id": now_part_of_cluster_id,
            },
        )
