from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_platform_mcp_server_exposes_mock_tool(http_client) -> None:
    metadata = await get_json(http_client, '/mcp/server')
    assert metadata.get('tools_endpoint') or metadata.get('name')
    result = await post_json(http_client, '/mcp/server/tools/mock-http-tool/call', {'arguments': {'input': 'e2e'}})
    assert result.get('result') is not None
