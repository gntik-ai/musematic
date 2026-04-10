from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from platform.search.projections import AgentSearchProjection, build_agent_aggregations, build_agent_query


pytestmark = pytest.mark.asyncio


def _agent(agent_id: int, workspace_id: str, capability: str, name: str | None = None) -> dict[str, object]:
    timestamp = (datetime.now(UTC) - timedelta(minutes=agent_id)).isoformat()
    return {
        "agent_id": f"agent-{agent_id}",
        "name": name or f"{capability.title()} Agent {agent_id}",
        "purpose": f"{capability} workflows for workspace {workspace_id}",
        "description": f"{capability} agent number {agent_id}",
        "tags": [capability, "automation"],
        "capabilities": [capability],
        "maturity_level": agent_id % 5,
        "trust_score": 0.5 + ((agent_id % 5) * 0.1),
        "workspace_id": workspace_id,
        "lifecycle_state": "active",
        "certification_status": "certified" if agent_id % 2 == 0 else "draft",
        "publisher_id": "publisher-1",
        "fqn": f"test:{workspace_id}:agent-{agent_id}",
        "indexed_at": timestamp,
        "updated_at": timestamp,
    }


async def test_marketplace_search_and_workspace_isolation(initialized_opensearch_client) -> None:
    projection = AgentSearchProjection(initialized_opensearch_client)
    documents: list[dict[str, object]] = []
    for index in range(50):
        workspace = "ws-1" if index < 20 else "ws-2" if index < 35 else "ws-3"
        capability = "summarization" if index % 3 == 0 else "translation" if index % 3 == 1 else "classification"
        documents.append(_agent(index, workspace, capability))
    documents.append(_agent(999, "ws-1", "summarization", name="Text Summary Agent"))

    result = await projection.bulk_reindex(documents)
    assert result.failed == 0
    await initialized_opensearch_client._client.indices.refresh(index="marketplace-agents-000001")

    search_result = await initialized_opensearch_client.search(
        index="marketplace-agents-*",
        query=build_agent_query("summarizer", workspace_id="ws-1"),
        workspace_id="ws-1",
        aggregations=build_agent_aggregations(),
        size=10,
    )
    assert search_result.total >= 1
    assert any(hit["workspace_id"] == "ws-1" for hit in search_result.hits)
    assert all(hit["workspace_id"] == "ws-1" for hit in search_result.hits)
    assert search_result.aggregations is not None
    buckets = search_result.aggregations["by_capability"]["buckets"]
    assert any(bucket["key"] == "summarization" for bucket in buckets)


async def test_search_after_paginates_without_cross_workspace_hits(initialized_opensearch_client) -> None:
    projection = AgentSearchProjection(initialized_opensearch_client)
    documents = [_agent(index, "ws-page", "translation") for index in range(15)]
    result = await projection.bulk_reindex(documents)
    assert result.failed == 0
    await initialized_opensearch_client._client.indices.refresh(index="marketplace-agents-000001")

    first_page = await initialized_opensearch_client.search_after(
        index="marketplace-agents-*",
        query={"match_all": {}},
        workspace_id="ws-page",
        sort=[{"agent_id": {"order": "asc"}}, {"_id": {"order": "asc"}}],
        size=5,
    )
    second_page = await initialized_opensearch_client.search_after(
        index="marketplace-agents-*",
        query={"match_all": {}},
        workspace_id="ws-page",
        sort=[{"agent_id": {"order": "asc"}}, {"_id": {"order": "asc"}}],
        search_after=first_page.search_after,
        size=5,
    )

    assert len(first_page.hits) == 5
    assert len(second_page.hits) == 5
    assert {hit["agent_id"] for hit in first_page.hits}.isdisjoint({hit["agent_id"] for hit in second_page.hits})
    assert all(hit["workspace_id"] == "ws-page" for hit in second_page.hits)
