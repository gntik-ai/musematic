from __future__ import annotations

import pytest

from suites._helpers import get_json, post_json


@pytest.mark.asyncio
async def test_hypothesis_proximity_graph_links_similar_items(http_client) -> None:
    first = await post_json(http_client, '/api/v1/discovery/hypotheses', {'text': 'E2E similar hypothesis alpha'})
    second = await post_json(http_client, '/api/v1/discovery/hypotheses', {'text': 'E2E similar hypothesis beta'})
    await post_json(http_client, '/api/v1/discovery/proximity-clusters/run', {})
    clusters = await get_json(http_client, '/api/v1/discovery/proximity-clusters')
    assert any(first.get('id') in str(cluster) and second.get('id') in str(cluster) for cluster in clusters.get('items', []))
