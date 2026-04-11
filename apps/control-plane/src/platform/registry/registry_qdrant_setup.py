from __future__ import annotations

from importlib import import_module
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings


async def create_agent_embeddings_collection(
    client: AsyncQdrantClient | None = None,
    settings: PlatformSettings | None = None,
) -> None:
    resolved_settings = settings or default_settings
    resolved_client = client or AsyncQdrantClient.from_settings(resolved_settings)
    should_close = client is None
    if should_close:
        await resolved_client.connect()
    try:
        qdrant_models = import_module("qdrant_client.models")
        await resolved_client.create_collection_if_not_exists(
            collection=resolved_settings.registry.embeddings_collection,
            vectors_config=qdrant_models.VectorParams(
                size=resolved_settings.registry.embedding_vector_size,
                distance=qdrant_models.Distance.COSINE,
            ),
            hnsw_config=qdrant_models.HnswConfigDiff(
                m=16,
                ef_construct=128,
                full_scan_threshold=10000,
            ),
            replication_factor=1,
            on_disk_payload=False,
        )
    finally:
        if should_close:
            await resolved_client.close()
