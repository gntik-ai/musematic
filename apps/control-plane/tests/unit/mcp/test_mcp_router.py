from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import PlatformError, platform_exception_handler
from platform.mcp.dependencies import get_mcp_service
from platform.mcp.models import MCPServerStatus
from platform.mcp.router import _require_operator
from platform.mcp.router import router as mcp_router
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI


class MCPServiceStub:
    def __init__(self) -> None:
        self.server_id = uuid4()
        self.workspace_id = uuid4()
        self.subject_id = uuid4()
        self.calls: list[tuple[str, object]] = []

    async def register_server(self, workspace_id, payload, subject):
        self.calls.append(("register_server", (workspace_id, payload.display_name, subject)))
        return {"server_id": str(self.server_id), "display_name": payload.display_name}

    async def list_servers(self, workspace_id, *, status, page, page_size):
        self.calls.append(("list_servers", (workspace_id, status, page, page_size)))
        return {
            "items": [{"server_id": str(self.server_id)}],
            "total": 1,
            "page": page,
            "page_size": page_size,
        }

    async def get_server(self, workspace_id, server_id):
        self.calls.append(("get_server", (workspace_id, server_id)))
        return {"server_id": str(server_id)}

    async def update_server(self, workspace_id, server_id, payload):
        self.calls.append(("update_server", (workspace_id, server_id, payload.status)))
        return {"server_id": str(server_id), "status": payload.status}

    async def deregister_server(self, workspace_id, server_id):
        self.calls.append(("deregister_server", (workspace_id, server_id)))
        return {"server_id": str(server_id), "status": "deregistered"}

    async def get_catalog(self, workspace_id, server_id):
        self.calls.append(("get_catalog", (workspace_id, server_id)))
        return {"server_id": str(server_id), "tool_count": 1, "tools": []}

    async def force_refresh(self, workspace_id, server_id):
        self.calls.append(("force_refresh", (workspace_id, server_id)))
        return {"server_id": str(server_id), "refresh_scheduled": True}

    async def list_exposed_tools(self, workspace_id, *, is_exposed, page, page_size):
        self.calls.append(("list_exposed_tools", (workspace_id, is_exposed, page, page_size)))
        return {
            "items": [{"tool_fqn": "finance:lookup", "mcp_tool_name": "lookup"}],
            "total": 1,
            "page": page,
            "page_size": page_size,
        }

    async def toggle_exposure(self, workspace_id, tool_fqn, payload, subject):
        self.calls.append(
            ("toggle_exposure", (workspace_id, tool_fqn, payload.is_exposed, subject))
        )
        return {"tool_fqn": tool_fqn, "mcp_tool_name": payload.mcp_tool_name}


def build_app(service: MCPServiceStub, principal: dict[str, object]) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(PlatformError, platform_exception_handler)

    async def _current_user() -> dict[str, object]:
        return principal

    async def _mcp_service() -> MCPServiceStub:
        return service

    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_mcp_service] = _mcp_service
    app.include_router(mcp_router)
    return app


def operator_principal(service: MCPServiceStub) -> dict[str, object]:
    return {
        "sub": str(service.subject_id),
        "workspace_id": str(service.workspace_id),
        "roles": [{"role": "operator"}],
    }


@pytest.mark.asyncio
async def test_mcp_router_operator_endpoints() -> None:
    service = MCPServiceStub()
    app = build_app(service, operator_principal(service))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        registered = await client.post(
            "/api/v1/mcp/servers",
            json={
                "display_name": "Finance MCP",
                "endpoint_url": "https://mcp.example.com",
                "auth_config": {"type": "api_key", "value": "secret"},
                "catalog_ttl_seconds": 120,
            },
        )
        listed = await client.get(
            "/api/v1/mcp/servers",
            params={"status": "active", "page": 2, "page_size": 5},
        )
        fetched = await client.get(f"/api/v1/mcp/servers/{service.server_id}")
        patched = await client.patch(
            f"/api/v1/mcp/servers/{service.server_id}",
            json={"status": "suspended"},
        )
        deleted = await client.delete(f"/api/v1/mcp/servers/{service.server_id}")
        catalog = await client.get(f"/api/v1/mcp/servers/{service.server_id}/catalog")
        refreshed = await client.post(f"/api/v1/mcp/servers/{service.server_id}/refresh")
        exposed = await client.get(
            "/api/v1/mcp/exposed-tools",
            params={"is_exposed": "true", "page": 3, "page_size": 7},
        )
        upserted = await client.put(
            "/api/v1/mcp/exposed-tools/finance:lookup",
            json={
                "mcp_tool_name": "lookup",
                "mcp_description": "Lookup records",
                "mcp_input_schema": {"type": "object"},
                "is_exposed": True,
            },
        )

    assert registered.status_code == 201
    assert listed.status_code == 200
    assert fetched.status_code == 200
    assert patched.status_code == 200
    assert deleted.status_code == 200
    assert catalog.status_code == 200
    assert refreshed.status_code == 202
    assert exposed.status_code == 200
    assert upserted.status_code == 200
    assert [name for name, _payload in service.calls] == [
        "register_server",
        "list_servers",
        "get_server",
        "update_server",
        "deregister_server",
        "get_catalog",
        "force_refresh",
        "list_exposed_tools",
        "toggle_exposure",
    ]
    assert service.calls[1][1][1] is MCPServerStatus.active


def test_require_operator_rejects_invalid_principals() -> None:
    with pytest.raises(PlatformError) as roles_error:
        _require_operator({"sub": str(uuid4()), "workspace_id": str(uuid4()), "roles": "operator"})
    assert roles_error.value.code == "UNAUTHORIZED"

    with pytest.raises(PlatformError) as missing_workspace_error:
        _require_operator({"sub": str(uuid4()), "roles": [{"role": "operator"}]})
    assert missing_workspace_error.value.code == "UNAUTHORIZED"

    with pytest.raises(PlatformError) as role_error:
        _require_operator(
            {
                "sub": str(uuid4()),
                "workspace_id": str(uuid4()),
                "roles": [{"role": "viewer"}],
            }
        )
    assert role_error.value.code == "UNAUTHORIZED"
