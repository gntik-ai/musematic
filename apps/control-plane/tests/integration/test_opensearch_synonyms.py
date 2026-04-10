from __future__ import annotations

import os

import pytest

from platform.search.projections import AgentSearchProjection, build_agent_aggregations, build_agent_query


pytestmark = pytest.mark.asyncio


async def test_synonym_expansion_and_facets(initialized_opensearch_client) -> None:
    projection = AgentSearchProjection(initialized_opensearch_client)
    await projection.index_agent(
        {
            "agent_id": "text-summary-agent",
            "name": "Text Summary Agent",
            "purpose": "Summarizes long-form text",
            "description": "A text summary agent with synonym coverage",
            "tags": ["summarization", "nlp"],
            "capabilities": ["summarization"],
            "maturity_level": 3,
            "trust_score": 0.92,
            "workspace_id": "ws-1",
            "lifecycle_state": "active",
            "certification_status": "certified",
            "publisher_id": "pub-1",
            "fqn": "test:text-summary-agent",
        }
    )
    await initialized_opensearch_client._client.indices.refresh(index="marketplace-agents-000001")

    result = await initialized_opensearch_client.search(
        index="marketplace-agents-*",
        query=build_agent_query("summarizer", workspace_id="ws-1"),
        workspace_id="ws-1",
        aggregations=build_agent_aggregations(),
        size=5,
    )
    assert any(hit["agent_id"] == "text-summary-agent" for hit in result.hits)
    assert result.aggregations is not None
    assert result.aggregations["by_capability"]["buckets"][0]["key"] == "summarization"


@pytest.mark.skipif(
    os.environ.get("RUN_LONG_OPENSEARCH_TESTS") != "1",
    reason="Requires live analyzer reload against a full OpenSearch runtime.",
)
async def test_synonym_dictionary_can_be_extended(initialized_opensearch_client) -> None:
    projection = AgentSearchProjection(initialized_opensearch_client)
    await projection.index_agent(
        {
            "agent_id": "compression-agent",
            "name": "Compression Agent",
            "purpose": "Compresses data streams",
            "description": "data compression agent",
            "tags": ["compression"],
            "capabilities": ["compression"],
            "maturity_level": 4,
            "trust_score": 0.88,
            "workspace_id": "ws-1",
            "lifecycle_state": "active",
            "certification_status": "certified",
            "publisher_id": "pub-2",
            "fqn": "test:compression-agent",
        }
    )
    await initialized_opensearch_client._client.indices.refresh(index="marketplace-agents-000001")

    before = await initialized_opensearch_client.search(
        index="marketplace-agents-*",
        query=build_agent_query("compressor", workspace_id="ws-1"),
        workspace_id="ws-1",
        size=5,
    )
    assert before.total == 0

    await initialized_opensearch_client._client.indices.close(index="marketplace-agents-000001")
    await initialized_opensearch_client._client.indices.put_settings(
        index="marketplace-agents-000001",
        body={
            "analysis": {
                "filter": {
                    "synonym_filter": {
                        "type": "synonym",
                        "synonyms": [
                            "summarizer, text summary agent, summarization",
                            "translator, language translation, translation agent",
                            "classifier, categorizer, classification agent",
                            "compressor, data compression agent",
                        ],
                    }
                }
            }
        },
    )
    await initialized_opensearch_client._client.indices.open(index="marketplace-agents-000001")
    await initialized_opensearch_client._client.indices.refresh(index="marketplace-agents-000001")

    after = await initialized_opensearch_client.search(
        index="marketplace-agents-*",
        query=build_agent_query("compressor", workspace_id="ws-1"),
        workspace_id="ws-1",
        size=5,
    )
    assert any(hit["agent_id"] == "compression-agent" for hit in after.hits)
