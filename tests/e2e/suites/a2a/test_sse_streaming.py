from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_a2a_sse_streaming_events_are_ordered(http_client, platform_api_url: str) -> None:
    headers = {'Authorization': f'Bearer {http_client.access_token}'}
    async with httpx.AsyncClient(base_url=platform_api_url, timeout=30.0, headers=headers) as client:
        async with client.stream('POST', '/a2a/tasks/stream', json={'agent_fqn': 'default:seeded-executor', 'input': 'stream'}) as stream:
            assert stream.status_code == 200
            events = [line async for line in stream.aiter_lines() if line.startswith('event:')]
    assert events[-1] in {'event: done', 'event: completed'}
