from __future__ import annotations

from importlib import import_module
from platform.common.config import PlatformSettings, Settings
from platform.common.config import settings as default_settings
from typing import Any
from uuid import UUID


class SimulationControllerClient:
    def __init__(self, target: str | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        self.target = target or self.settings.GRPC_SIMULATION_CONTROLLER
        self.channel: Any | None = None
        self.stub: Any | None = None

    @classmethod
    def from_settings(cls, settings: PlatformSettings) -> SimulationControllerClient:
        return cls(settings=settings)

    async def connect(self) -> None:
        if self.channel is not None:
            return
        grpc = import_module("grpc")
        self.channel = grpc.aio.insecure_channel(self.target)
        self.stub = self.channel

    async def close(self) -> None:
        if self.channel is None:
            return
        close = getattr(self.channel, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result
        self.channel = None
        self.stub = None

    async def health_check(self) -> bool:
        try:
            await self.connect()
            state_fn = getattr(self.channel, "get_state", None)
            if state_fn is None:
                return True
            state = state_fn(try_to_connect=True)
            return "SHUTDOWN" not in str(state)
        except Exception:
            return False

    async def create_simulation(
        self,
        *,
        workspace_id: UUID,
        twin_configs: list[dict[str, Any]],
        scenario_config: dict[str, Any],
        max_duration_seconds: int,
    ) -> Any:
        await self.connect()
        method = self._method("create_simulation", "CreateSimulation")
        payload = {
            "workspace_id": str(workspace_id),
            "twin_configs": twin_configs,
            "scenario_config": scenario_config,
            "max_duration_seconds": max_duration_seconds,
        }
        result = method(payload)
        if hasattr(result, "__await__"):
            result = await result
        return result

    async def get_simulation(self, controller_run_id: str) -> Any:
        await self.connect()
        method = self._method("get_simulation", "GetSimulation")
        result = method({"controller_run_id": controller_run_id})
        if hasattr(result, "__await__"):
            result = await result
        return result

    async def cancel_simulation(self, controller_run_id: str) -> None:
        await self.connect()
        method = self._method("cancel_simulation", "CancelSimulation")
        result = method({"controller_run_id": controller_run_id})
        if hasattr(result, "__await__"):
            await result

    async def get_simulation_artifacts(self, controller_run_id: str) -> Any:
        await self.connect()
        method = self._method("get_simulation_artifacts", "GetSimulationArtifacts")
        result = method({"controller_run_id": controller_run_id})
        if hasattr(result, "__await__"):
            result = await result
        return result

    def _method(self, *names: str) -> Any:
        if self.stub is None:
            raise RuntimeError("Simulation controller client is not connected")
        for name in names:
            method = getattr(self.stub, name, None)
            if method is not None:
                return method
        raise RuntimeError(f"Simulation controller method unavailable: {', '.join(names)}")
