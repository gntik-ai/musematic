import pytest

pytestmark = pytest.mark.asyncio


async def test_cluster_health_single_node(initialized_opensearch_client) -> None:
    health = await initialized_opensearch_client.health_check()
    assert health.status in {"yellow", "green"}
    assert health.nodes == 1


async def test_agent_analyzer_exposes_synonym_tokens(initialized_opensearch_client) -> None:
    response = await initialized_opensearch_client._client.indices.analyze(
        index="marketplace-agents-000001",
        body={"analyzer": "agent_analyzer", "text": "summarizer"},
    )
    tokens = [token["token"] for token in response["tokens"]]
    assert "summarizer" in tokens
    assert any(token in {"summary", "summarization"} for token in tokens)
