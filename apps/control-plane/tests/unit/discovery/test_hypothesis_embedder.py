from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.discovery.models import Hypothesis
from platform.discovery.proximity.embeddings import HypothesisEmbedder
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_embed_hypothesis_upserts_qdrant_point(monkeypatch: pytest.MonkeyPatch) -> None:
    hypothesis = Hypothesis(
        id=uuid4(),
        workspace_id=uuid4(),
        session_id=uuid4(),
        title="h",
        description="d",
        reasoning="r",
        confidence=0.8,
        generating_agent_fqn="agent",
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"data": [{"embedding": [0.1, 0.2, 0.3]}]},
    )

    class FakeAsyncClient:
        async def __aenter__(self):
            return SimpleNamespace(post=AsyncMock(return_value=response))

        async def __aexit__(self, *args):
            return None

    client = FakeAsyncClient()
    monkeypatch.setattr("httpx.AsyncClient", lambda **_: client)
    qdrant = SimpleNamespace(
        create_collection_if_not_exists=AsyncMock(),
        create_payload_index=AsyncMock(),
        upsert_vectors=AsyncMock(),
    )
    repo = SimpleNamespace(session=SimpleNamespace(flush=AsyncMock()))
    embedder = HypothesisEmbedder(settings=PlatformSettings(), qdrant=qdrant, repository=repo)
    monkeypatch.setattr(embedder, "ensure_collection", AsyncMock())

    vector = await embedder.embed_hypothesis(hypothesis)

    assert vector == [0.1, 0.2, 0.3]
    assert hypothesis.qdrant_point_id == str(hypothesis.id)
    qdrant.upsert_vectors.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_collection_fetch_and_invalid_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeModels:
        class Distance:
            COSINE = "Cosine"

        class PayloadSchemaType:
            KEYWORD = "keyword"

        class VectorParams:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class HnswConfigDiff:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class MatchValue:
            def __init__(self, value):
                self.value = value

        class FieldCondition:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class Filter:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

    monkeypatch.setattr(
        "platform.discovery.proximity.embeddings.import_module",
        lambda _: FakeModels,
    )
    point = SimpleNamespace(id="p1", vector=[0.1], payload={"hypothesis_id": "p1"})
    raw_client = SimpleNamespace(scroll=AsyncMock(return_value=([point], None)))
    qdrant = SimpleNamespace(
        create_collection_if_not_exists=AsyncMock(),
        create_payload_index=AsyncMock(),
        _ensure_client=AsyncMock(return_value=raw_client),
    )
    embedder = HypothesisEmbedder(
        settings=PlatformSettings(),
        qdrant=qdrant,
        repository=SimpleNamespace(session=SimpleNamespace(flush=AsyncMock())),
    )

    await embedder.ensure_collection()
    embeddings = await embedder.fetch_session_embeddings(uuid4(), uuid4())

    assert embeddings == [{"id": "p1", "vector": [0.1], "payload": {"hypothesis_id": "p1"}}]
    assert qdrant.create_payload_index.await_count == 4

    bad_response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"data": [{}]})

    class FakeAsyncClient:
        async def __aenter__(self):
            return SimpleNamespace(post=AsyncMock(return_value=bad_response))

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr("httpx.AsyncClient", lambda **_: FakeAsyncClient())
    with pytest.raises(ValueError, match="embedding"):
        await embedder._embed_text("bad")
