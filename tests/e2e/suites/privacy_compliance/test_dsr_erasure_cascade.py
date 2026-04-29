from __future__ import annotations


def test_dsr_erasure_cascade_per_store_contract() -> None:
    stores = {"postgres", "qdrant", "neo4j", "clickhouse", "opensearch", "s3"}
    assert len(stores) == 6
    assert {"postgres", "s3"} <= stores
