from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


COLLECTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "agent_embeddings": (
        ("workspace_id", "keyword"),
        ("agent_id", "keyword"),
        ("lifecycle_state", "keyword"),
        ("maturity_level", "integer"),
        ("tags", "keyword"),
    ),
    "memory_embeddings": (
        ("workspace_id", "keyword"),
        ("agent_id", "keyword"),
        ("scope", "keyword"),
        ("memory_type", "keyword"),
        ("freshness_score", "float"),
    ),
    "pattern_embeddings": (
        ("workspace_id", "keyword"),
        ("pattern_type", "keyword"),
        ("promoted", "bool"),
    ),
    "test_similarity": (
        ("workspace_id", "keyword"),
        ("agent_id", "keyword"),
        ("test_suite_id", "keyword"),
    ),
}

PAYLOAD_TYPES = {
    "keyword": "KEYWORD",
    "integer": "INTEGER",
    "float": "FLOAT",
    "bool": "BOOL",
}


async def main() -> None:
    from platform.common.clients.qdrant import AsyncQdrantClient
    from platform.common.config import Settings

    settings = Settings()
    qdrant_models = __import__("qdrant_client.models", fromlist=["models"])
    replication_factor = int(__import__("os").environ.get("QDRANT_REPLICATION_FACTOR", "2"))
    vectors_config = qdrant_models.VectorParams(
        size=settings.QDRANT_COLLECTION_DIMENSIONS,
        distance=qdrant_models.Distance.COSINE,
    )
    hnsw_config = qdrant_models.HnswConfigDiff(m=16, ef_construct=128, full_scan_threshold=10000)

    created: list[str] = []
    existing: list[str] = []
    async with AsyncQdrantClient(settings) as client:
        for collection, indexes in COLLECTIONS.items():
            was_created = await client.create_collection_if_not_exists(
                collection=collection,
                vectors_config=vectors_config,
                hnsw_config=hnsw_config,
                replication_factor=replication_factor,
            )
            (created if was_created else existing).append(collection)
            for field_name, field_type in indexes:
                await client.create_payload_index(
                    collection=collection,
                    field_name=field_name,
                    field_type=getattr(qdrant_models.PayloadSchemaType, PAYLOAD_TYPES[field_type]),
                )

    print(f"created={created}")
    print(f"existing={existing}")


if __name__ == "__main__":
    asyncio.run(main())
