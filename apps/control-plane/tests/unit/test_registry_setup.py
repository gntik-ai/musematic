from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.registry.registry_opensearch_setup import create_marketplace_agents_index
from platform.registry.registry_qdrant_setup import create_agent_embeddings_collection
from types import SimpleNamespace

import pytest

from tests.registry_support import AsyncOpenSearchStub, AsyncQdrantStub


@pytest.mark.asyncio
async def test_opensearch_setup_creates_template_backing_index_and_alias() -> None:
    indices = _IndicesStub()
    client = AsyncOpenSearchStub(raw_client=SimpleNamespace(indices=indices))

    await create_marketplace_agents_index(client, PlatformSettings())
    await create_marketplace_agents_index(client, PlatformSettings())

    assert indices.templates
    assert indices.created == ["marketplace-agents-000001"]
    assert indices.aliases[0]["name"] == "marketplace-agents"


@pytest.mark.asyncio
async def test_qdrant_setup_creates_collection_with_expected_dimensions(monkeypatch) -> None:
    settings = PlatformSettings(REGISTRY_EMBEDDING_VECTOR_SIZE=64)
    client = AsyncQdrantStub()
    qdrant_models = SimpleNamespace(
        Distance=SimpleNamespace(COSINE="cosine"),
        VectorParams=lambda size, distance: {"size": size, "distance": distance},
        HnswConfigDiff=lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        "platform.registry.registry_qdrant_setup.import_module",
        lambda name: qdrant_models,
    )

    await create_agent_embeddings_collection(client, settings)

    assert client.create_calls[0]["collection"] == settings.registry.embeddings_collection
    assert client.create_calls[0]["vectors_config"]["size"] == 64


@pytest.mark.asyncio
async def test_setup_uses_default_client_factories_and_skips_existing_alias(monkeypatch) -> None:
    opensearch_client = AsyncOpenSearchStub(
        raw_client=SimpleNamespace(indices=_ExistingAliasIndicesStub())
    )
    qdrant_client = AsyncQdrantStub()
    monkeypatch.setattr(
        "platform.registry.registry_opensearch_setup.AsyncOpenSearchClient.from_settings",
        lambda settings: opensearch_client,
    )
    monkeypatch.setattr(
        "platform.registry.registry_qdrant_setup.AsyncQdrantClient.from_settings",
        lambda settings: qdrant_client,
    )
    qdrant_models = SimpleNamespace(
        Distance=SimpleNamespace(COSINE="cosine"),
        VectorParams=lambda size, distance: {"size": size, "distance": distance},
        HnswConfigDiff=lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        "platform.registry.registry_qdrant_setup.import_module",
        lambda name: qdrant_models,
    )

    await create_marketplace_agents_index(None, PlatformSettings())
    await create_agent_embeddings_collection(None, PlatformSettings())

    assert opensearch_client.connected is True
    assert opensearch_client.closed is True
    assert qdrant_client.connected is True
    assert qdrant_client.closed is True


class _IndicesStub:
    def __init__(self) -> None:
        self.templates: list[dict[str, object]] = []
        self.created: list[str] = []
        self.aliases: list[dict[str, object]] = []
        self.exists_calls = 0

    async def put_index_template(self, **kwargs):
        self.templates.append(kwargs)

    async def exists(self, **kwargs):
        self.exists_calls += 1
        return self.exists_calls > 1

    async def create(self, **kwargs):
        self.created.append(kwargs["index"])

    async def get_alias(self, **kwargs):
        return {kwargs["index"]: {"aliases": {}}}

    async def put_alias(self, **kwargs):
        self.aliases.append(kwargs)


class _ExistingAliasIndicesStub(_IndicesStub):
    async def exists(self, **kwargs):
        return True

    async def get_alias(self, **kwargs):
        return {kwargs["index"]: {"aliases": {"marketplace-agents": {"is_write_index": True}}}}
