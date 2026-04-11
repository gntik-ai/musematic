from __future__ import annotations

from importlib import import_module
from platform.common.clients.neo4j import AsyncNeo4jClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.config import PlatformSettings
from platform.common.config import settings as default_settings


async def setup_memory_collections(
    qdrant_client: AsyncQdrantClient | None = None,
    neo4j_client: AsyncNeo4jClient | None = None,
    settings: PlatformSettings | None = None,
) -> None:
    resolved_settings = settings or default_settings
    resolved_qdrant = qdrant_client or AsyncQdrantClient.from_settings(resolved_settings)
    resolved_neo4j = neo4j_client or AsyncNeo4jClient.from_settings(resolved_settings)
    should_close_qdrant = qdrant_client is None
    should_close_neo4j = neo4j_client is None

    try:
        if should_close_qdrant:
            await resolved_qdrant.connect()
        if should_close_neo4j:
            await resolved_neo4j.connect()

        qdrant_models = import_module("qdrant_client.models")
        await resolved_qdrant.create_collection_if_not_exists(
            collection="platform_memory",
            vectors_config=qdrant_models.VectorParams(
                size=resolved_settings.memory.embedding_dimensions,
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
        for field_name in ("workspace_id", "agent_fqn", "scope"):
            await resolved_qdrant.create_payload_index(
                collection="platform_memory",
                field_name=field_name,
                field_schema=qdrant_models.PayloadSchemaType.KEYWORD,
            )

        if resolved_neo4j.mode != "local":
            await resolved_neo4j.run_cypher(
                "CREATE INDEX node_workspace IF NOT EXISTS FOR (n:MemoryNode) ON (n.workspace_id)"
            )
            await resolved_neo4j.run_cypher(
                "CREATE CONSTRAINT node_unique IF NOT EXISTS "
                "FOR (n:MemoryNode) REQUIRE (n.workspace_id, n.pg_id) IS UNIQUE"
            )
    finally:
        if should_close_neo4j:
            await resolved_neo4j.close()
        if should_close_qdrant:
            await resolved_qdrant.close()
