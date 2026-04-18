from __future__ import annotations

from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.execution.dependencies import get_runtime_controller_client
from platform.execution.router import runtime_router

import httpx
import pytest
from fastapi import FastAPI


class RuntimeControllerStub(RuntimeControllerClient):
    def __init__(self) -> None:
        self.status_calls: list[tuple[str, str]] = []
        self.config_calls: list[tuple[str, str, int]] = []

    async def warm_pool_status(
        self, workspace_id: str = "", agent_type: str = ""
    ) -> dict[str, object]:
        self.status_calls.append((workspace_id, agent_type))
        return {
            "keys": [
                {
                    "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
                    "agent_type": "python-3.12",
                    "target_size": 3,
                    "available_count": 2,
                    "dispatched_count": 1,
                    "warming_count": 0,
                    "last_dispatch_at": None,
                }
            ]
        }

    async def warm_pool_config(
        self,
        workspace_id: str,
        agent_type: str,
        target_size: int,
    ) -> dict[str, object]:
        self.config_calls.append((workspace_id, agent_type, target_size))
        return {"accepted": True, "message": ""}


def build_app(
    current_user: dict[str, object], runtime_controller: RuntimeControllerStub
) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)

    async def _current_user() -> dict[str, object]:
        return current_user

    async def _runtime_controller() -> RuntimeControllerStub:
        return runtime_controller

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_runtime_controller_client] = _runtime_controller
    app.include_router(runtime_router)
    return app


@pytest.mark.asyncio
async def test_warm_pool_status_endpoint_requires_admin() -> None:
    runtime_controller = RuntimeControllerStub()
    app = build_app({"sub": "user-1", "roles": []}, runtime_controller)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/runtime/warm-pool/status")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_warm_pool_status_endpoint_returns_keys_for_admin() -> None:
    runtime_controller = RuntimeControllerStub()
    app = build_app(
        {"sub": "user-1", "roles": [{"role": "platform_admin"}]},
        runtime_controller,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/runtime/warm-pool/status",
            params={
                "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
                "agent_type": "python-3.12",
            },
        )

    assert response.status_code == 200
    assert response.json()["keys"][0]["available_count"] == 2
    assert runtime_controller.status_calls == [
        ("550e8400-e29b-41d4-a716-446655440000", "python-3.12")
    ]


@pytest.mark.asyncio
async def test_warm_pool_config_endpoint_validates_and_updates() -> None:
    runtime_controller = RuntimeControllerStub()
    app = build_app(
        {"sub": "user-1", "roles": [{"role": "platform_admin"}]},
        runtime_controller,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        ok_response = await client.put(
            "/api/v1/runtime/warm-pool/config",
            json={
                "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
                "agent_type": "python-3.12",
                "target_size": 5,
            },
        )
        bad_response = await client.put(
            "/api/v1/runtime/warm-pool/config",
            json={
                "workspace_id": "550e8400-e29b-41d4-a716-446655440000",
                "agent_type": "python-3.12",
                "target_size": -1,
            },
        )

    assert ok_response.status_code == 200
    assert ok_response.json() == {"accepted": True, "message": ""}
    assert runtime_controller.config_calls == [
        ("550e8400-e29b-41d4-a716-446655440000", "python-3.12", 5)
    ]
    assert bad_response.status_code == 422
