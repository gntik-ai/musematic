from __future__ import annotations

import json
from platform.common.clients.mcp_client import MCPClient
from platform.mcp.exceptions import (
    MCPProtocolVersionError,
    MCPServerUnavailableError,
    MCPToolError,
)

import httpx
import pytest


@pytest.mark.asyncio
async def test_client_initializes_lists_and_calls_tools_with_expected_headers() -> None:
    calls: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.headers["x-api-key"] == "secret"
        body = json.loads(request.content.decode("utf-8"))
        if request.url.path == "/initialize":
            assert body["protocolVersion"] == "2024-11-05"
            return httpx.Response(
                200,
                json={
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "demo"},
                },
            )
        if request.url.path == "/tools/list":
            return httpx.Response(
                200,
                json={
                    "tools": [
                        {
                            "name": "search",
                            "description": "Search remote data",
                            "inputSchema": {"type": "object"},
                        }
                    ]
                },
            )
        assert request.url.path == "/tools/call"
        assert body["name"] == "search"
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "ok"}],
                "structuredContent": {"hits": 1},
                "isError": False,
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_handler),
        base_url="https://mcp.example.com",
    ) as http_client:
        client = MCPClient(
            "https://mcp.example.com",
            {"type": "api_key", "value": "secret", "header_name": "x-api-key"},
            http_client=http_client,
        )
        capabilities = await client.initialize()
        tools = await client.list_tools()
        result = await client.call_tool("search", {"query": "revenue"})

    assert capabilities.protocol_version == "2024-11-05"
    assert [tool.name for tool in tools] == ["search"]
    assert result.structured_content == {"hits": 1}
    assert result.is_error is False
    assert calls == ["/initialize", "/tools/list", "/tools/call"]


@pytest.mark.asyncio
async def test_client_rejects_protocol_mismatch() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "protocolVersion": "1999-01-01",
                    "capabilities": {},
                    "serverInfo": {"name": "legacy"},
                },
            )
        ),
        base_url="https://mcp.example.com",
    ) as http_client:
        client = MCPClient(
            "https://mcp.example.com",
            http_client=http_client,
        )
        with pytest.raises(MCPProtocolVersionError):
            await client.initialize()


@pytest.mark.asyncio
async def test_client_classifies_transient_permanent_and_tool_errors() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503, json={})),
        base_url="https://mcp.example.com",
    ) as http_client:
        client = MCPClient("https://mcp.example.com", http_client=http_client)
        with pytest.raises(MCPServerUnavailableError) as transient:
            await client.initialize()

    assert transient.value.classification == "transient"
    assert transient.value.retry_safe is True

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not-json")),
        base_url="https://mcp.example.com",
    ) as http_client:
        client = MCPClient("https://mcp.example.com", http_client=http_client)
        with pytest.raises(MCPServerUnavailableError) as permanent:
            await client.initialize()

    assert permanent.value.classification == "permanent"
    assert permanent.value.retry_safe is False

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "error": {
                        "code": "tool_failed",
                        "message": "remote failure",
                        "data": {"classification": "permanent"},
                    }
                },
            )
        ),
        base_url="https://mcp.example.com",
    ) as http_client:
        client = MCPClient("https://mcp.example.com", http_client=http_client)
        client._initialized = object()  # type: ignore[assignment]
        with pytest.raises(MCPToolError) as tool_error:
            await client.call_tool("search", {})

    assert tool_error.value.code == "tool_failed"
    assert tool_error.value.classification == "permanent"


@pytest.mark.asyncio
async def test_client_handles_timeouts_and_supports_header_modes() -> None:
    class TimeoutTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            del request
            raise httpx.ReadTimeout("timeout")

    async with httpx.AsyncClient(
        transport=TimeoutTransport(),
        base_url="https://mcp.example.com",
    ) as http_client:
        client = MCPClient("https://mcp.example.com", http_client=http_client)
        with pytest.raises(MCPServerUnavailableError) as error:
            await client.initialize()

    assert error.value.classification == "transient"
    assert client._headers() == {"Content-Type": "application/json"}
    assert MCPClient(
        "https://mcp.example.com",
        {"type": "bearer", "token": "token"},
    )._headers()["Authorization"] == "Bearer token"
    assert MCPClient(
        "https://mcp.example.com",
        {"type": "headers", "headers": {"x-tenant": "finance"}},
    )._headers()["x-tenant"] == "finance"


@pytest.mark.asyncio
async def test_client_handles_invalid_payload_shapes_and_close_paths() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json=(
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "serverInfo": {"name": "demo"},
                    }
                    if request.url.path == "/initialize"
                    else {"tools": {}}
                ),
            )
        ),
        base_url="https://mcp.example.com",
    ) as http_client:
        client = MCPClient("https://mcp.example.com", http_client=http_client)
        with pytest.raises(MCPServerUnavailableError) as invalid_tools:
            await client.list_tools()

    assert invalid_tools.value.classification == "permanent"

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=["invalid"])),
        base_url="https://mcp.example.com",
    ) as http_client:
        client = MCPClient("https://mcp.example.com", http_client=http_client)
        with pytest.raises(MCPServerUnavailableError) as invalid_payload:
            await client.initialize()

    assert invalid_payload.value.classification == "permanent"

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"error": "boom"})
        ),
        base_url="https://mcp.example.com",
    ) as http_client:
        client = MCPClient("https://mcp.example.com", http_client=http_client)
        client._initialized = object()  # type: ignore[assignment]
        with pytest.raises(MCPToolError) as generic_tool_error:
            await client.call_tool("search", {})

    assert generic_tool_error.value.code == "mcp_error"

    close_calls: list[str] = []

    class ClosingClient:
        async def aclose(self) -> None:
            close_calls.append("closed")

    client = MCPClient("https://mcp.example.com")
    client.http_client = ClosingClient()  # type: ignore[assignment]
    await client.close()

    assert close_calls == ["closed"]
    assert MCPClient(
        "https://mcp.example.com",
        {"type": "api_key", "value": ""},
    )._headers() == {"Content-Type": "application/json"}
    assert MCPClient(
        "https://mcp.example.com",
        {"type": "bearer", "token": ""},
    )._headers() == {"Content-Type": "application/json"}
