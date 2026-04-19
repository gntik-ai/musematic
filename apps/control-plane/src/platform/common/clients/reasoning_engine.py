from __future__ import annotations

from importlib import import_module
from platform.common.config import PlatformSettings, Settings
from platform.common.config import settings as default_settings
from typing import Any, cast


class ReasoningEngineClient:
    def __init__(self, target: str | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        self.target = target or self.settings.GRPC_REASONING_ENGINE
        self.channel: Any | None = None
        self.stub: Any | None = None

    @classmethod
    def from_settings(cls, settings: PlatformSettings) -> ReasoningEngineClient:
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

    async def get_reasoning_trace(
        self,
        execution_id: str,
        step_id: str | None = None,
    ) -> dict[str, Any] | None:
        response = await self._invoke(
            "GetReasoningTrace",
            {"execution_id": execution_id, "step_id": step_id or ""},
            not_found_is_none=True,
        )
        if response is None:
            return None
        return self._normalize_response(response)

    async def _invoke(
        self,
        method_name: str,
        request: dict[str, Any],
        *,
        not_found_is_none: bool = False,
    ) -> Any:
        await self.connect()
        target = getattr(self.stub, method_name, None)
        if not callable(target):
            raise AttributeError(f"reasoning engine stub does not implement {method_name}")
        try:
            result = target(request)
            if hasattr(result, "__await__"):
                return await result
            return result
        except Exception as exc:
            code = getattr(exc, "code", None)
            if not_found_is_none and callable(code):
                value = code()
                if str(value).endswith("NOT_FOUND"):
                    return None
            raise

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
