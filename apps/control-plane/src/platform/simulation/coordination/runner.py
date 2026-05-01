from __future__ import annotations

from platform.common.clients.simulation_controller import SimulationControllerClient
from platform.simulation.events import SimulationEventPublisher
from platform.simulation.exceptions import (
    SimulationInfrastructureUnavailableError,
    SimulationNotCancellableError,
    SimulationNotFoundError,
)
from platform.simulation.models import SimulationRun
from platform.simulation.repository import SimulationRepository
from typing import Any
from uuid import UUID


class SimulationRunner:
    def __init__(
        self,
        *,
        repository: SimulationRepository,
        controller_client: SimulationControllerClient | Any | None,
        publisher: SimulationEventPublisher,
    ) -> None:
        self.repository = repository
        self.controller_client = controller_client
        self.publisher = publisher

    async def create(
        self,
        *,
        workspace_id: UUID,
        name: str,
        description: str | None,
        digital_twin_ids: list[UUID],
        twin_configs: list[dict[str, Any]],
        scenario_config: dict[str, Any],
        max_duration_seconds: int,
        isolation_policy_id: UUID | None,
        initiated_by: UUID,
        scenario_id: UUID | None = None,
    ) -> SimulationRun:
        response = await self._create_controller_run(
            workspace_id=workspace_id,
            twin_configs=twin_configs,
            scenario_config=scenario_config,
            max_duration_seconds=max_duration_seconds,
        )
        run = await self.repository.create_run(
            SimulationRun(
                workspace_id=workspace_id,
                name=name,
                description=description,
                digital_twin_ids=[str(item) for item in digital_twin_ids],
                scenario_config=scenario_config,
                isolation_policy_id=isolation_policy_id,
                scenario_id=scenario_id,
                controller_run_id=_field(response, "controller_run_id"),
                status="provisioning",
                results={"provisioning_events": _field(response, "provisioning_events", [])},
                initiated_by=initiated_by,
            )
        )
        await self.repository.set_status_cache(
            run.id,
            {"status": run.status, "progress_pct": 0, "current_step": "provisioning"},
        )
        await self.publisher.simulation_run_created(
            run.id,
            workspace_id,
            initiated_by,
            run.controller_run_id,
        )
        return run

    async def cancel(
        self,
        run_id: UUID,
        workspace_id: UUID,
        *,
        actor_id: UUID | None = None,
    ) -> SimulationRun:
        run = await self.repository.get_run(run_id, workspace_id)
        if run is None:
            raise SimulationNotFoundError("Simulation run", run_id)
        if run.status not in {"provisioning", "running"}:
            raise SimulationNotCancellableError(run.id, run.status)
        await self._cancel_controller_run(run)
        updated = await self.repository.update_run_status(run.id, workspace_id, "cancelled")
        assert updated is not None
        await self.repository.set_status_cache(
            run.id,
            {"status": "cancelled", "progress_pct": 100, "current_step": "cancelled"},
        )
        await self.publisher.simulation_run_cancelled(run.id, workspace_id, actor_id)
        return updated

    async def _create_controller_run(
        self,
        *,
        workspace_id: UUID,
        twin_configs: list[dict[str, Any]],
        scenario_config: dict[str, Any],
        max_duration_seconds: int,
    ) -> Any:
        if self.controller_client is None:
            raise SimulationInfrastructureUnavailableError(
                "simulation_controller",
                "client is not configured",
            )
        create = getattr(self.controller_client, "create_simulation", None)
        if create is None:
            raise SimulationInfrastructureUnavailableError(
                "simulation_controller",
                "create_simulation is not available",
            )
        try:
            return await create(
                workspace_id=workspace_id,
                twin_configs=twin_configs,
                scenario_config=scenario_config,
                max_duration_seconds=max_duration_seconds,
            )
        except Exception as exc:
            raise SimulationInfrastructureUnavailableError(
                "simulation_controller",
                str(exc),
            ) from exc

    async def _cancel_controller_run(self, run: SimulationRun) -> None:
        if self.controller_client is None or run.controller_run_id is None:
            return
        cancel = getattr(self.controller_client, "cancel_simulation", None)
        if cancel is None:
            raise SimulationInfrastructureUnavailableError(
                "simulation_controller",
                "cancel_simulation is not available",
            )
        try:
            await cancel(run.controller_run_id)
        except Exception as exc:
            raise SimulationInfrastructureUnavailableError(
                "simulation_controller",
                str(exc),
            ) from exc


def _field(value: Any, name: str, default: Any | None = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)
