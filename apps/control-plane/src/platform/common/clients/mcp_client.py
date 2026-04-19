from __future__ import annotations

import json
from platform.mcp.exceptions import MCPProtocolVersionError, MCPServerUnavailableError, MCPToolError
from platform.mcp.schemas import MCPCapabilities, MCPToolDefinition, MCPToolResult
from typing import Any, cast

import httpx


class MCPClient:
    def __init__(
        self,
        base_url: str,
        auth_config: dict[str, Any] | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_config = auth_config or {}
        self.timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.AsyncClient(timeout=timeout_seconds)
        self._initialized: MCPCapabilities | None = None

    async def close(self) -> None:
        if self._owns_client:
            await self.http_client.aclose()

    async def initialize(self) -> MCPCapabilities:
        response = await self._post_json(
            "/initialize",
            {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}},
        )
        capabilities = MCPCapabilities.model_validate(response)
        if capabilities.protocol_version != "2024-11-05":
            raise MCPProtocolVersionError(["2024-11-05"])
        self._initialized = capabilities
        return capabilities

    async def list_tools(self) -> list[MCPToolDefinition]:
        if self._initialized is None:
            await self.initialize()
        response = await self._post_json("/tools/list", {})
        tools = response.get("tools", [])
        if not isinstance(tools, list):
            raise MCPServerUnavailableError(
                "MCP tools/list returned an invalid payload",
                classification="permanent",
                retry_safe=False,
            )
        return [MCPToolDefinition.model_validate(item) for item in tools]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> MCPToolResult:
        if self._initialized is None:
            await self.initialize()
        response = await self._post_json(
            "/tools/call",
            {"name": name, "arguments": arguments},
        )
        return MCPToolResult.model_validate(response)

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self.http_client.post(
                f"{self.base_url}{path}",
                json=payload,
                headers=self._headers(),
            )
        except httpx.TimeoutException as exc:
            raise MCPServerUnavailableError(
                "MCP server timed out",
                classification="transient",
                retry_safe=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise MCPServerUnavailableError(
                "MCP server connection failed",
                classification="transient",
                retry_safe=True,
            ) from exc

        if response.status_code >= 500:
            raise MCPServerUnavailableError(
                f"MCP server returned HTTP {response.status_code}",
                classification="transient",
                retry_safe=True,
            )
        try:
            data = cast(dict[str, Any], response.json())
        except (ValueError, json.JSONDecodeError) as exc:
            raise MCPServerUnavailableError(
                "MCP server returned invalid JSON",
                classification="permanent",
                retry_safe=False,
            ) from exc
        if not isinstance(data, dict):
            raise MCPServerUnavailableError(
                "MCP server returned an invalid payload",
                classification="permanent",
                retry_safe=False,
            )
        if "error" in data:
            error = data.get("error")
            if isinstance(error, dict):
                raise MCPToolError(
                    str(error.get("code", "mcp_error")),
                    str(error.get("message", "MCP tool invocation failed")),
                    classification=str(
                        error.get("data", {}).get("classification", "permanent")
                    ),
                )
            raise MCPToolError(
                "mcp_error",
                "MCP tool invocation failed",
                classification="permanent",
            )
        return data

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        auth_type = str(self.auth_config.get("type", "")).strip().lower()
        if auth_type == "api_key":
            name = str(self.auth_config.get("header_name", "x-api-key"))
            value = str(self.auth_config.get("value", ""))
            if value:
                headers[name] = value
        elif auth_type == "bearer":
            token = str(self.auth_config.get("token", ""))
            if token:
                headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "headers":
            for key, value in dict(self.auth_config.get("headers", {})).items():
                headers[str(key)] = str(value)
        return headers
