from __future__ import annotations

from importlib import import_module
from platform.common.config import PlatformSettings, Settings
from platform.common.config import settings as default_settings
from typing import Any


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
