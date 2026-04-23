from __future__ import annotations

from importlib import import_module
from platform.common.config import PlatformSettings, Settings
from platform.common.config import settings as default_settings
from typing import Any, cast

_runtime_controller_pb2: Any = import_module("platform.common.clients.runtime_controller_pb2")
_runtime_controller_pb2_grpc: Any = import_module(
    "platform.common.clients.runtime_controller_pb2_grpc"
)
_protobuf_json_format: Any = import_module("google.protobuf.json_format")


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

    async def list_active_instances(self, agent_fqn: str) -> list[str]:
        stub = await self._get_stub()
        target = getattr(stub, "ListActiveInstances", None)
        if callable(target):
            response = await self._invoke("ListActiveInstances", {"agent_fqn": agent_fqn})
            instances = response.get("execution_ids") if isinstance(response, dict) else None
            return [str(item) for item in (instances or [])]
        return []

    async def stop_runtime(
        self,
        execution_id: str,
        *,
        grace_period_seconds: int = 30,
    ) -> dict[str, Any]:
        response = await self._invoke(
            "StopRuntime",
            {"execution_id": execution_id, "grace_period_seconds": grace_period_seconds},
        )
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

    async def _get_stub(self) -> Any:
        await self.connect()
        if self.stub is None:
            assert self.channel is not None
            self.stub = _runtime_controller_pb2_grpc.RuntimeControlServiceStub(self.channel)
        return self.stub

    async def _invoke(self, method_name: str, request: dict[str, Any]) -> Any:
        stub = await self._get_stub()
        target = getattr(stub, method_name, None)
        if not callable(target):
            raise AttributeError(f"runtime controller stub does not implement {method_name}")
        result = target(self._build_request(stub, method_name, request))
        if hasattr(result, "__await__"):
            return await result
        return result

    def _build_request(self, stub: Any, method_name: str, request: dict[str, Any]) -> Any:
        if not self._uses_generated_stub(stub):
            return request
        factory = self._request_factory(method_name)
        if factory is None:
            return request
        return _protobuf_json_format.ParseDict(request, factory(), ignore_unknown_fields=False)

    @staticmethod
    def _uses_generated_stub(stub: Any) -> bool:
        module_name = type(stub).__module__
        return module_name.startswith(
            (_runtime_controller_pb2_grpc.__name__, "platform.grpc_stubs.")
        )

    @staticmethod
    def _request_factory(method_name: str) -> Any:
        factories = {
            "LaunchRuntime": _runtime_controller_pb2.LaunchRuntimeRequest,
            "StopRuntime": _runtime_controller_pb2.StopRuntimeRequest,
            "WarmPoolStatus": _runtime_controller_pb2.WarmPoolStatusRequest,
            "WarmPoolConfig": _runtime_controller_pb2.WarmPoolConfigRequest,
        }
        return factories.get(method_name)

    def _normalize_response(self, response: Any) -> dict[str, Any]:
        if isinstance(response, dict):
            return response
        if hasattr(response, "DESCRIPTOR"):
            return cast(
                dict[str, Any],
                _protobuf_json_format.MessageToDict(response, preserving_proto_field_name=True),
            )
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
