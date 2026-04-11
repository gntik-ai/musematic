from __future__ import annotations

from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace

import pytest
from botocore.exceptions import ClientError

from platform.common.clients.clickhouse import AsyncClickHouseClient
from platform.common.clients.neo4j import AsyncNeo4jClient
from platform.common.clients.object_storage import AsyncObjectStorageClient
from platform.common.clients.opensearch import AsyncOpenSearchClient
from platform.common.clients.qdrant import AsyncQdrantClient
from platform.common.clients.reasoning_engine import ReasoningEngineClient
from platform.common.clients.redis import AsyncRedisClient
from platform.common.clients.runtime_controller import RuntimeControllerClient
from platform.common.clients.sandbox_manager import SandboxManagerClient
from platform.common.clients.simulation_controller import SimulationControllerClient
from platform.common.config import PlatformSettings


class FakeRedisBackend:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def ping(self) -> bool:
        return True

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: bytes, ex=None) -> None:
        self.values[key] = value

    async def delete(self, key: str) -> int:
        self.values.pop(key, None)
        return 1

    async def hgetall(self, key: str):
        return {"field": "value"}

    async def evalsha(self, sha: str, key_count: int, *values):
        return {"sha": sha, "values": values}

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_redis_client_methods() -> None:
    settings = PlatformSettings(REDIS_URL="redis://redis:6379")
    client = AsyncRedisClient.from_settings(settings)
    client.client = FakeRedisBackend()

    await client.set("key", b"value", ttl=5)

    assert await client.health_check() is True
    assert await client.get("key") == b"value"
    assert await client.hgetall("hash") == {"field": "value"}
    assert await client.evalsha("abc", ["k"], ["v"]) == {"sha": "abc", "values": ("k", "v")}


@pytest.mark.asyncio
async def test_qdrant_client_methods(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeAsyncQdrantClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        async def get_collections(self):
            return []

        async def upsert(self, **kwargs) -> None:
            calls["upsert"] = kwargs

        async def search(self, **kwargs):
            calls["search"] = kwargs
            return [SimpleNamespace(id="p1", score=0.9, payload={"name": "point"})]

        async def create_collection(self, **kwargs) -> None:
            calls["create_collection"] = kwargs

        async def close(self) -> None:
            return None

    fake_models = SimpleNamespace(
        PointStruct=lambda **kwargs: SimpleNamespace(**kwargs),
        VectorParams=lambda **kwargs: SimpleNamespace(**kwargs),
        Distance=SimpleNamespace(COSINE="cosine"),
    )
    monkeypatch.setattr(
        "platform.common.clients.qdrant.import_module",
        lambda name: SimpleNamespace(AsyncQdrantClient=FakeAsyncQdrantClient)
        if name == "qdrant_client"
        else fake_models,
    )

    client = AsyncQdrantClient(PlatformSettings(QDRANT_URL="http://qdrant:6333"))
    await client.connect()
    await client.upsert_vectors("vectors", [{"id": "1", "vector": [0.1], "payload": {"a": 1}}])
    result = await client.search_vectors("vectors", [0.1], 5)
    await client.create_collection("vectors", 10, "cosine")

    assert await client.health_check() is True
    assert result[0]["id"] == "p1"
    assert "upsert" in calls and "create_collection" in calls


@pytest.mark.asyncio
async def test_neo4j_client_methods(monkeypatch) -> None:
    class FakeTransaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def run(self, query, params=None):
            return None

        async def commit(self) -> None:
            return None

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def run(self, query, params=None):
            return SimpleNamespace(single=_single)

        async def begin_transaction(self):
            return FakeTransaction()

    class FakeDriver:
        def session(self):
            return FakeSession()

        async def close(self) -> None:
            return None

    client = AsyncNeo4jClient(PlatformSettings(NEO4J_URL="bolt://neo4j:7687", GRAPH_MODE="neo4j"))
    monkeypatch.setattr(client, "_get_driver", _async_result(FakeDriver()))
    monkeypatch.setattr(client, "run_query", _async_result([{"ok": 1}]))

    await client.connect()
    assert await client.run_cypher("RETURN 1") == [{"ok": 1}]
    await client.run_in_transaction([("RETURN 1", {})])
    assert await client.health_check() is True


@pytest.mark.asyncio
async def test_clickhouse_client_methods(monkeypatch) -> None:
    class FakeResult:
        column_names = ["ok"]
        result_rows = [(1,)]

    class FakeClient:
        async def query(self, sql, parameters=None):
            return FakeResult()

        async def insert(self, table, rows, column_names=None):
            return None

    client = AsyncClickHouseClient(PlatformSettings(CLICKHOUSE_URL="http://clickhouse:8123"))
    monkeypatch.setattr(client, "_get_client", _async_result(FakeClient()))

    assert await client.execute_query("SELECT 1") == [{"ok": 1}]
    await client.insert("table", [{"ok": 1}], ["ok"])
    assert await client.health_check() is True


@pytest.mark.asyncio
async def test_opensearch_client_methods(monkeypatch) -> None:
    class FakeAsyncOpenSearch:
        def __init__(self, **kwargs) -> None:
            self.cluster = SimpleNamespace(health=_async_result({"status": "green"}))

        async def index(self, **kwargs):
            return {"_id": kwargs["id"]}

        async def search(self, **kwargs):
            return {"hits": {"hits": []}}

        async def close(self) -> None:
            return None

    helpers = SimpleNamespace(async_bulk=_async_result((1, [])))
    monkeypatch.setattr(
        "platform.common.clients.opensearch.import_module",
        lambda name: SimpleNamespace(AsyncOpenSearch=FakeAsyncOpenSearch)
        if name == "opensearchpy"
        else helpers,
    )

    client = AsyncOpenSearchClient(PlatformSettings(OPENSEARCH_HOSTS="http://search:9200"))
    await client.connect()
    assert await client.health_check() is True
    await client.index("items", "1", {"name": "doc"})
    assert await client.search("items", {"match_all": {}}, size=5) == {"hits": {"hits": []}}
    assert await client.bulk([{"_index": "items", "_source": {"id": "1"}}]) == {"success": 1, "errors": []}


@pytest.mark.asyncio
async def test_object_storage_client_methods(monkeypatch) -> None:
    class FakeBody:
        async def read(self) -> bytes:
            return b"payload"

    class FakeS3:
        def __init__(self) -> None:
            self.created_bucket = False

        async def put_object(self, **kwargs) -> None:
            return None

        async def get_object(self, **kwargs):
            return {"Body": FakeBody()}

        async def list_objects_v2(self, **kwargs):
            return {"Contents": [{"Key": "a.txt", "Size": 1, "LastModified": None, "ETag": '"a"'}]}

        async def head_bucket(self, **kwargs) -> None:
            raise ClientError({"Error": {"Code": "NoSuchBucket"}}, "HeadBucket")

        async def create_bucket(self, **kwargs) -> None:
            self.created_bucket = True

        async def list_buckets(self):
            return {"Buckets": [{"Name": "bucket"}]}

    fake_s3 = FakeS3()
    client = AsyncObjectStorageClient(PlatformSettings(MINIO_ENDPOINT="http://minio:9000"))

    @asynccontextmanager
    async def fake_client():
        yield fake_s3

    monkeypatch.setattr(client, "_client", fake_client)
    monkeypatch.setattr(client, "_get_session", lambda: object())
    await client.connect()
    await client.put_object("bucket", "key", b"payload")
    assert await client.get_object("bucket", "key") == b"payload"
    assert await client.list_objects("bucket") == ["a.txt"]
    await client.create_bucket_if_not_exists("bucket")
    assert await client.health_check() is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module_path", "class_name"),
    [
        ("platform.common.clients.runtime_controller", "RuntimeControllerClient"),
        ("platform.common.clients.reasoning_engine", "ReasoningEngineClient"),
        ("platform.common.clients.sandbox_manager", "SandboxManagerClient"),
        ("platform.common.clients.simulation_controller", "SimulationControllerClient"),
    ],
)
async def test_grpc_wrappers(module_path: str, class_name: str, monkeypatch) -> None:
    module = __import__(module_path, fromlist=[class_name, "import_module"])
    wrapper_cls = getattr(module, class_name)

    class FakeChannel:
        def get_state(self, try_to_connect: bool = True):  # noqa: ARG002
            return "READY"

        async def close(self) -> None:
            return None

    fake_grpc = ModuleType("grpc")
    fake_grpc.aio = SimpleNamespace(insecure_channel=lambda target: FakeChannel())
    monkeypatch.setattr(module, "import_module", lambda name: fake_grpc)

    client = wrapper_cls(settings=PlatformSettings())
    await client.connect()

    assert await client.health_check() is True
    await client.close()


async def _single():
    return {"ok": 1}


def _async_result(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner
