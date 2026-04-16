from __future__ import annotations

from enum import StrEnum
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.events.registry import event_registry
from platform.simulation.models import SimulationRun
from platform.simulation.repository import SimulationRepository
from typing import Any, Final
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict


class SimulationEventType(StrEnum):
    simulation_run_created = "simulation_run_created"
    simulation_run_cancelled = "simulation_run_cancelled"
    simulation_run_started = "simulation_run_started"
    simulation_run_completed = "simulation_run_completed"
    simulation_run_failed = "simulation_run_failed"
    simulation_run_timeout = "simulation_run_timeout"
    twin_created = "twin_created"
    twin_modified = "twin_modified"
    prediction_completed = "prediction_completed"
    comparison_completed = "comparison_completed"
    isolation_breach_detected = "isolation_breach_detected"


class SimulationEventPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    simulation_id: UUID | None = None
    run_id: UUID | None = None
    workspace_id: UUID | None = None


SIMULATION_EVENT_SCHEMAS: Final[dict[str, type[BaseModel]]] = {
    event_type.value: SimulationEventPayload for event_type in SimulationEventType
}


def register_simulation_event_types() -> None:
    for event_type, schema in SIMULATION_EVENT_SCHEMAS.items():
        event_registry.register(event_type, schema)


class SimulationEventPublisher:
    def __init__(self, producer: EventProducer | None) -> None:
        self.producer = producer

    async def publish(
        self,
        event_type: SimulationEventType | str,
        *,
        key_id: UUID,
        workspace_id: UUID,
        payload: dict[str, Any] | None = None,
        correlation_ctx: CorrelationContext | None = None,
    ) -> None:
        if self.producer is None:
            return
        event_name = event_type.value if isinstance(event_type, SimulationEventType) else event_type
        enriched = {
            "simulation_id": key_id,
            "workspace_id": workspace_id,
            **(payload or {}),
        }
        await self.producer.publish(
            topic="simulation.events",
            key=str(key_id),
            event_type=event_name,
            payload=enriched,
            correlation_ctx=correlation_ctx
            or CorrelationContext(workspace_id=workspace_id, correlation_id=uuid4()),
            source="platform.simulation",
        )

    async def simulation_run_created(
        self,
        run_id: UUID,
        workspace_id: UUID,
        actor_id: UUID,
        controller_run_id: str | None,
    ) -> None:
        await self.publish(
            SimulationEventType.simulation_run_created,
            key_id=run_id,
            workspace_id=workspace_id,
            payload={
                "run_id": run_id,
                "actor_id": actor_id,
                "controller_run_id": controller_run_id,
            },
        )

    async def simulation_run_cancelled(
        self,
        run_id: UUID,
        workspace_id: UUID,
        actor_id: UUID | None = None,
    ) -> None:
        await self.publish(
            SimulationEventType.simulation_run_cancelled,
            key_id=run_id,
            workspace_id=workspace_id,
            payload={"run_id": run_id, "actor_id": actor_id},
        )

    async def twin_created(self, twin_id: UUID, workspace_id: UUID, agent_fqn: str) -> None:
        await self.publish(
            SimulationEventType.twin_created,
            key_id=twin_id,
            workspace_id=workspace_id,
            payload={"twin_id": twin_id, "agent_fqn": agent_fqn},
        )

    async def twin_modified(
        self,
        twin_id: UUID,
        workspace_id: UUID,
        parent_twin_id: UUID,
        version: int,
    ) -> None:
        await self.publish(
            SimulationEventType.twin_modified,
            key_id=twin_id,
            workspace_id=workspace_id,
            payload={"twin_id": twin_id, "parent_twin_id": parent_twin_id, "version": version},
        )

    async def prediction_completed(
        self,
        prediction_id: UUID,
        workspace_id: UUID,
        status: str,
    ) -> None:
        await self.publish(
            SimulationEventType.prediction_completed,
            key_id=prediction_id,
            workspace_id=workspace_id,
            payload={"prediction_id": prediction_id, "status": status},
        )

    async def comparison_completed(
        self,
        report_id: UUID,
        workspace_id: UUID,
        compatible: bool,
    ) -> None:
        await self.publish(
            SimulationEventType.comparison_completed,
            key_id=report_id,
            workspace_id=workspace_id,
            payload={"report_id": report_id, "compatible": compatible},
        )

    async def isolation_breach_detected(
        self,
        run_id: UUID,
        workspace_id: UUID,
        breach_event: dict[str, Any],
    ) -> None:
        await self.publish(
            SimulationEventType.isolation_breach_detected,
            key_id=run_id,
            workspace_id=workspace_id,
            payload={"run_id": run_id, "breach": breach_event},
        )


class SimulationEventsConsumer:
    def __init__(
        self,
        repository: SimulationRepository,
        *,
        release_isolation: Any | None = None,
    ) -> None:
        self.repository = repository
        self.release_isolation = release_isolation

    async def handle_event(self, envelope: Any) -> None:
        event_type = str(getattr(envelope, "event_type", ""))
        payload = dict(getattr(envelope, "payload", envelope if isinstance(envelope, dict) else {}))
        if not event_type:
            event_type = str(payload.get("event_type", ""))
        if event_type not in {
            SimulationEventType.simulation_run_started.value,
            SimulationEventType.simulation_run_completed.value,
            SimulationEventType.simulation_run_failed.value,
            SimulationEventType.simulation_run_timeout.value,
        }:
            return
        run_id = _payload_uuid(payload, "run_id") or _payload_uuid(payload, "simulation_id")
        workspace_id = _payload_uuid(payload, "workspace_id")
        if run_id is None or workspace_id is None:
            return
        status = {
            SimulationEventType.simulation_run_started.value: "running",
            SimulationEventType.simulation_run_completed.value: "completed",
            SimulationEventType.simulation_run_failed.value: "failed",
            SimulationEventType.simulation_run_timeout.value: "timeout",
        }[event_type]
        run = await self.repository.update_run_status(
            run_id,
            workspace_id,
            status,
            results=payload.get("results") if isinstance(payload.get("results"), dict) else None,
        )
        await self.repository.set_status_cache(
            run_id,
            {
                "status": status,
                "progress_pct": payload.get("progress_pct", 100 if status == "completed" else 0),
                "current_step": payload.get("current_step", status),
            },
        )
        if run is not None and status in {"completed", "failed", "timeout"}:
            await self._release(run)

    async def _release(self, run: SimulationRun) -> None:
        if self.release_isolation is None:
            return
        result = self.release_isolation(run)
        if hasattr(result, "__await__"):
            await result


def _payload_uuid(payload: dict[str, Any], key: str) -> UUID | None:
    value = payload.get(key)
    if value is None:
        return None
    return value if isinstance(value, UUID) else UUID(str(value))
