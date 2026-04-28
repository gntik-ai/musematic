from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_mcp_client_discovery_and_gateway_call(http_client) -> None:
    tools = await get_json(http_client, '/mcp/tools')
    assert any(tool.get('name') == 'mock-http-tool' for tool in tools.get('items', tools))
    result = await post_json(http_client, '/mcp/call', {'tool': 'mock-http-tool', 'arguments': {'input': 'e2e'}})
    assert result.get('result') is not None
