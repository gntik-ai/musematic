from __future__ import annotations

from platform.common.clients import runtime_controller_pb2, runtime_controller_pb2_grpc
from platform.common.clients.runtime_controller import RuntimeControllerClient

import pytest


class RuntimeControllerStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def LaunchRuntime(  # noqa: N802
        self, request: dict[str, object]
    ) -> dict[str, object]:
        self.calls.append(("LaunchRuntime", request))
        return {"runtime_id": "runtime-1", "warm_start": bool(request.get("prefer_warm"))}

    async def WarmPoolStatus(  # noqa: N802
        self, request: dict[str, object]
    ) -> dict[str, object]:
        self.calls.append(("WarmPoolStatus", request))
        return {
            "keys": [
                {
                    "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
                    "agent_type": "python-3.12",
                    "target_size": 2,
                    "available_count": 1,
                    "dispatched_count": 1,
                    "warming_count": 0,
                    "last_dispatch_at": None,
                }
            ]
        }

    async def WarmPoolConfig(  # noqa: N802
        self, request: dict[str, object]
    ) -> dict[str, object]:
        self.calls.append(("WarmPoolConfig", request))
        return {"accepted": True, "message": ""}


@pytest.mark.asyncio
async def test_runtime_controller_client_launch_runtime_includes_prefer_warm() -> None:
    client = RuntimeControllerClient(target="runtime-controller:50051")
    client.channel = object()
    client.stub = RuntimeControllerStub()

    result = await client.launch_runtime({"execution_id": "exec-1"}, prefer_warm=True)

    assert result["warm_start"] is True
    assert client.stub.calls[0] == (
        "LaunchRuntime",
        {"contract": {"execution_id": "exec-1"}, "prefer_warm": True},
    )


@pytest.mark.asyncio
async def test_runtime_controller_client_warm_pool_status_calls_stub() -> None:
    client = RuntimeControllerClient(target="runtime-controller:50051")
    client.channel = object()
    client.stub = RuntimeControllerStub()

    result = await client.warm_pool_status(
        workspace_id="550e8400-e29b-41d4-a716-446655440000",
        agent_type="python-3.12",
    )

    assert result["keys"][0]["target_size"] == 2
    assert client.stub.calls[0] == (
        "WarmPoolStatus",
        {
            "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
            "agent_type": "python-3.12",
        },
    )


@pytest.mark.asyncio
async def test_runtime_controller_client_warm_pool_config_calls_stub() -> None:
    client = RuntimeControllerClient(target="runtime-controller:50051")
    client.channel = object()
    client.stub = RuntimeControllerStub()

    result = await client.warm_pool_config(
        "550e8400-e29b-41d4-a716-446655440000",
        "python-3.12",
        5,
    )

    assert result == {"accepted": True, "message": ""}
    assert client.stub.calls[0] == (
        "WarmPoolConfig",
        {
            "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
            "agent_type": "python-3.12",
            "target_size": 5,
        },
    )


class GeneratedRuntimeControlServiceStub:
    __module__ = runtime_controller_pb2_grpc.__name__


def test_runtime_controller_client_builds_generated_launch_request() -> None:
    client = RuntimeControllerClient(target="runtime-controller:50051")
    request = client._build_request(
        GeneratedRuntimeControlServiceStub(),
        "LaunchRuntime",
        {
            "contract": {
                "agent_revision": "ns:a",
                "model_binding": "{}",
                "policy_ids": [],
                "correlation_context": {
                    "workspace_id": "ws-1",
                    "execution_id": "exec-1",
                },
                "resource_limits": {},
                "task_plan_json": "{}",
                "step_id": "step-a",
            },
            "prefer_warm": True,
        },
    )

    assert isinstance(request, runtime_controller_pb2.LaunchRuntimeRequest)
    assert request.contract.correlation_context.workspace_id == "ws-1"
    assert request.contract.correlation_context.execution_id == "exec-1"
    assert request.contract.agent_revision == "ns:a"
    assert request.prefer_warm is True
