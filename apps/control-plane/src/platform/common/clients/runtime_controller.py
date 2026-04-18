from __future__ import annotations

from importlib import import_module
from platform.common.config import PlatformSettings, Settings
from platform.common.config import settings as default_settings
from typing import Any, cast


class RuntimeControllerClient:
    def __init__(self, target: str | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        self.target = target or self.settings.GRPC_RUNTIME_CONTROLLER
        self.channel: Any | None = None
        self.stub: Any | None = None

    @classmethod
    def from_settings(cls, settings: PlatformSettings) -> RuntimeControllerClient:
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

    async def launch_runtime(
        self,
        payload: dict[str, Any],
        *,
        prefer_warm: bool = True,
    ) -> dict[str, Any]:
        request = {"contract": dict(payload), "prefer_warm": prefer_warm}
        response = await self._invoke("LaunchRuntime", request)
        return self._normalize_response(response)

    async def warm_pool_status(
        self,
        workspace_id: str = "",
        agent_type: str = "",
    ) -> dict[str, Any]:
        response = await self._invoke(
            "WarmPoolStatus",
            {"workspace_id": workspace_id, "agent_type": agent_type},
        )
        return self._normalize_response(response)

    async def warm_pool_config(
        self,
        workspace_id: str,
        agent_type: str,
        target_size: int,
    ) -> dict[str, Any]:
        response = await self._invoke(
            "WarmPoolConfig",
            {
                "workspace_id": workspace_id,
                "agent_type": agent_type,
                "target_size": target_size,
            },
        )
        return self._normalize_response(response)

    async def _invoke(self, method_name: str, request: dict[str, Any]) -> Any:
        await self.connect()
        target = getattr(self.stub, method_name, None)
        if not callable(target):
            raise AttributeError(f"runtime controller stub does not implement {method_name}")
        result = target(request)
        if hasattr(result, "__await__"):
            return await result
        return result

    def _normalize_response(self, response: Any) -> dict[str, Any]:
        if isinstance(response, dict):
            return response
        model_dump = getattr(response, "model_dump", None)
        if callable(model_dump):
            return cast(dict[str, Any], model_dump(mode="json"))
        to_dict = getattr(response, "to_dict", None)
        if callable(to_dict):
            return cast(dict[str, Any], to_dict())
        keys = getattr(response, "keys", None)
        if keys is not None and callable(keys):
            return {key: getattr(response, key) for key in keys()}
        data: dict[str, Any] = {}
        for field in dir(response):
            if field.startswith("_"):
                continue
            value = getattr(response, field)
            if callable(value):
                continue
            data[field] = value
        return data
