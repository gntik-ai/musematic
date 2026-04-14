from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from redis.exceptions import RedisError

from platform.common.clients.redis import AsyncRedisClient, BudgetConfig
from platform.common.config import PlatformSettings


def _build_client() -> SimpleNamespace:
    return SimpleNamespace(
        aclose=AsyncMock(),
        close=AsyncMock(),
        delete=AsyncMock(return_value=1),
        eval=AsyncMock(return_value=["eval"]),
        evalsha=AsyncMock(return_value=["evalsha"]),
        expire=AsyncMock(),
        get=AsyncMock(return_value=None),
        hgetall=AsyncMock(return_value={"field": "value"}),
        hset=AsyncMock(),
        ping=AsyncMock(return_value=True),
        scan=AsyncMock(return_value=(0, [])),
        script_load=AsyncMock(side_effect=["sha-budget", "sha-rate", "sha-lock-a", "sha-lock-r"]),
        set=AsyncMock(),
        zadd=AsyncMock(),
        zrem=AsyncMock(return_value=1),
        zrevrange=AsyncMock(return_value=[("hyp-a", 1200.0)]),
        zrevrank=AsyncMock(return_value=2),
        zscore=AsyncMock(return_value=1500.0),
    )


def test_from_settings_uses_nested_redis_configuration() -> None:
    settings = PlatformSettings.model_validate(
        {
            "REDIS_NODES": ["cache-a:6379", "cache-b:6379"],
            "REDIS_PASSWORD": "topsecret",
            "REDIS_TEST_MODE": "standalone",
            "REDIS_URL": "redis://cache-a:6379",
        }
    )

    client = AsyncRedisClient.from_settings(settings)

    assert client.nodes == ["cache-a:6379", "cache-b:6379"]
    assert client.password == "topsecret"
    assert client._standalone is True
    assert client._url == "redis://cache-a:6379"


def test_from_settings_falls_back_to_redis_url_when_nodes_are_missing() -> None:
    settings = PlatformSettings.model_validate(
        {
            "REDIS_NODES": [],
            "REDIS_URL": "redis://fallback-cache:6380",
        }
    )

    client = AsyncRedisClient.from_settings(settings)

    assert client.nodes == ["fallback-cache:6380"]
    assert client.password is None
    assert client._standalone is (settings.REDIS_TEST_MODE == "standalone")


@pytest.mark.asyncio
async def test_initialize_uses_standalone_url_and_preloads_scripts(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _build_client()
    from_url = MagicMock(return_value=fake_client)

    monkeypatch.setattr("platform.common.clients.redis.Redis.from_url", from_url)
    monkeypatch.setattr(
        AsyncRedisClient,
        "_script_source",
        lambda self, script_name: f"-- {script_name}",
    )

    client = AsyncRedisClient(nodes=["localhost:6379"])
    client._standalone = True
    client._url = "redis://localhost:6379"

    await client.initialize()
    await client.initialize()

    assert client.client is fake_client
    from_url.assert_called_once_with("redis://localhost:6379", decode_responses=True)
    assert fake_client.script_load.await_count == 4


@pytest.mark.asyncio
async def test_initialize_uses_standalone_host_and_port_without_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _build_client()
    redis_ctor = MagicMock(return_value=fake_client)

    monkeypatch.setattr("platform.common.clients.redis.Redis", redis_ctor)
    monkeypatch.setattr(
        AsyncRedisClient,
        "_script_source",
        lambda self, script_name: f"-- {script_name}",
    )

    client = AsyncRedisClient(nodes=["localhost:6380"], password="pw")
    client._standalone = True
    client._url = None

    await client.initialize()

    redis_ctor.assert_called_once_with(
        host="localhost",
        port=6380,
        password="pw",
        decode_responses=True,
    )
    assert client.client is fake_client


@pytest.mark.asyncio
async def test_initialize_uses_cluster_when_not_in_standalone(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _build_client()
    from_url = MagicMock(return_value=fake_client)

    monkeypatch.setattr("platform.common.clients.redis.RedisCluster.from_url", from_url)
    monkeypatch.setattr(
        AsyncRedisClient,
        "_script_source",
        lambda self, script_name: f"-- {script_name}",
    )

    client = AsyncRedisClient(nodes=["cluster-a:6379"], password="pw")
    client._standalone = False
    client._url = None

    await client.initialize()

    assert client.client is fake_client
    from_url.assert_called_once_with(
        "redis://:pw@cluster-a:6379",
        password="pw",
        max_connections=32,
        decode_responses=True,
        require_full_coverage=False,
    )


@pytest.mark.asyncio
async def test_initialize_uses_explicit_cluster_url(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _build_client()
    from_url = MagicMock(return_value=fake_client)

    monkeypatch.setattr("platform.common.clients.redis.RedisCluster.from_url", from_url)
    monkeypatch.setattr(
        AsyncRedisClient,
        "_script_source",
        lambda self, script_name: f"-- {script_name}",
    )

    client = AsyncRedisClient(nodes=["cluster-a:6379"], password="pw")
    client._standalone = False
    client._url = "redis://cluster-bootstrap:6379"

    await client.initialize()

    from_url.assert_called_once_with(
        "redis://cluster-bootstrap:6379",
        password="pw",
        max_connections=32,
        decode_responses=True,
        require_full_coverage=False,
    )


@pytest.mark.asyncio
async def test_close_supports_aclose_and_close_fallback() -> None:
    aclose_client = _build_client()
    close_client = SimpleNamespace(close=AsyncMock())

    client = AsyncRedisClient(nodes=["localhost:6379"])
    client.client = aclose_client
    await client.close()
    aclose_client.aclose.assert_awaited_once()
    assert client.client is None

    client.client = close_client
    await client.close()
    close_client.close.assert_awaited_once()
    assert client.client is None


@pytest.mark.asyncio
async def test_close_returns_when_client_is_missing() -> None:
    client = AsyncRedisClient(nodes=["localhost:6379"])

    await client.close()

    assert client.client is None


@pytest.mark.asyncio
async def test_health_check_and_primitive_wrappers() -> None:
    fake_client = _build_client()
    fake_client.get.side_effect = [None, "value", b"raw-bytes"]
    client = AsyncRedisClient(nodes=["localhost:6379"])
    client.client = fake_client

    assert await client.health_check() is True
    assert await client.get("missing") is None
    assert await client.get("key") == b"value"
    assert await client.get("key") == b"raw-bytes"
    await client.set("key", b"payload", ttl=30)
    await client.delete("key")
    assert await client.hgetall("hash") == {"field": "value"}
    assert await client.evalsha("sha", ["key"], ["arg"]) == ["evalsha"]

    fake_client.set.assert_awaited_once_with("key", b"payload", ex=30)
    fake_client.delete.assert_any_await("key")


@pytest.mark.asyncio
async def test_health_check_returns_false_on_redis_error() -> None:
    fake_client = _build_client()
    fake_client.ping.side_effect = RedisError("down")
    client = AsyncRedisClient(nodes=["localhost:6379"])
    client.client = fake_client

    assert await client.health_check() is False


@pytest.mark.asyncio
async def test_connect_delegates_to_initialize(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AsyncRedisClient(nodes=["localhost:6379"])
    initialize = AsyncMock()

    monkeypatch.setattr(client, "initialize", initialize)

    await client.connect()

    initialize.assert_awaited_once()


@pytest.mark.asyncio
async def test_session_helpers_and_invalidate_user_sessions() -> None:
    fake_client = _build_client()
    fake_client.get.side_effect = ['{"role":"owner"}', None]
    fake_client.delete.side_effect = [1, 2]
    fake_client.scan.side_effect = [(7, ["session:u1:s1", "session:u1:s2"]), (0, [])]
    client = AsyncRedisClient(nodes=["localhost:6379"])
    client.client = fake_client

    await client.set_session("u1", "s1", {"role": "owner"}, ttl_seconds=600)
    assert await client.get_session("u1", "s1") == {"role": "owner"}
    assert await client.get_session("u1", "s2") is None
    assert await client.delete_session("u1", "s1") is True
    assert await client.invalidate_user_sessions("u1") == 2

    fake_client.set.assert_awaited_once_with("session:u1:s1", '{"role": "owner"}', ex=600)
    fake_client.scan.assert_any_await(cursor=0, match="session:u1:*", count=100)


@pytest.mark.asyncio
async def test_invalidate_user_sessions_handles_empty_scan_page() -> None:
    fake_client = _build_client()
    fake_client.scan.side_effect = [(0, [])]
    client = AsyncRedisClient(nodes=["localhost:6379"])
    client.client = fake_client

    assert await client.invalidate_user_sessions("u2") == 0
    fake_client.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_budget_helpers_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _build_client()
    fake_client.hgetall.side_effect = [
        {"max_tokens": "10", "used_tokens": "2"},
        {},
    ]
    fake_client.delete.return_value = 0
    client = AsyncRedisClient(nodes=["localhost:6379"])
    client.client = fake_client

    monkeypatch.setattr("platform.common.clients.redis.time.time", lambda: 100.5)
    eval_script = AsyncMock(return_value=["1", "8", "4", "1.5", "900"])
    monkeypatch.setattr(client, "_eval_script", eval_script)

    config = BudgetConfig(max_tokens=10, max_rounds=5, max_cost=3.5, max_time_ms=1500)
    await client.init_budget("exec-1", "step-1", config, ttl_seconds=30)
    result = await client.decrement_budget("exec-1", "step-1", "tokens", 2)

    assert result.allowed is True
    assert result.remaining_tokens == 8
    assert result.remaining_rounds == 4
    assert result.remaining_cost == 1.5
    assert result.remaining_time_ms == 900
    assert await client.get_budget("exec-1", "step-1") == {"max_tokens": "10", "used_tokens": "2"}
    assert await client.get_budget("exec-1", "step-1") is None
    assert await client.delete_budget("exec-1", "step-1") is False

    fake_client.hset.assert_awaited_once_with(
        "budget:exec-1:step-1",
        mapping={
            "max_tokens": 10,
            "used_tokens": 0,
            "max_rounds": 5,
            "used_rounds": 0,
            "max_cost": 3.5,
            "used_cost": 0,
            "max_time_ms": 1500,
            "start_time": 100500,
        },
    )
    fake_client.expire.assert_awaited_once_with("budget:exec-1:step-1", 30)
    eval_script.assert_awaited_once_with(
        fake_client,
        "budget_decrement.lua",
        ["budget:exec-1:step-1"],
        [100500, "tokens", 2],
    )


@pytest.mark.asyncio
async def test_rate_limit_and_lock_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _build_client()
    client = AsyncRedisClient(nodes=["localhost:6379"])
    client.client = fake_client

    monkeypatch.setattr("platform.common.clients.redis.time.time", lambda: 200.0)
    monkeypatch.setattr("platform.common.clients.redis.uuid.uuid4", lambda: "token-123")
    eval_script = AsyncMock(side_effect=[["0", "1", "250"], "1", "0"])
    monkeypatch.setattr(client, "_eval_script", eval_script)

    rate_result = await client.check_rate_limit("workspace", "abc", limit=5, window_ms=5000)
    lock_result = await client.acquire_lock("workflow", "run-1", ttl_seconds=15)
    released = await client.release_lock("workflow", "run-1", "token-123")

    assert rate_result.allowed is False
    assert rate_result.remaining == 1
    assert rate_result.retry_after_ms == 250
    assert lock_result.success is True
    assert lock_result.token == "token-123"
    assert released is False
    assert eval_script.await_args_list[0].args == (
        fake_client,
        "rate_limit_check.lua",
        ["ratelimit:workspace:abc"],
        [200000, 5000, 5],
    )


@pytest.mark.asyncio
async def test_leaderboard_add_top_rank_and_score_none() -> None:
    fake_client = _build_client()
    fake_client.zrevrange.return_value = [("hyp-a", 1200.0), ("hyp-b", 1185)]
    fake_client.zrevrank.return_value = None
    fake_client.zscore.return_value = None
    client = AsyncRedisClient(nodes=["localhost:6379"])
    client.client = fake_client

    await client.leaderboard_add("tour-1", "hyp-a", 1200.0)
    assert await client.leaderboard_top("tour-1", 2) == [("hyp-a", 1200.0), ("hyp-b", 1185.0)]
    assert await client.leaderboard_rank("tour-1", "hyp-a") is None
    assert await client.leaderboard_score("tour-1", "hyp-a") is None

    fake_client.zadd.assert_awaited_once_with("leaderboard:tour-1", {"hyp-a": 1200.0})
    fake_client.zrevrange.assert_awaited_once_with("leaderboard:tour-1", 0, 1, withscores=True)


@pytest.mark.asyncio
async def test_cache_helpers_and_leaderboard_helpers() -> None:
    fake_client = _build_client()
    fake_client.get.side_effect = ['{"cached": true}', None]
    fake_client.delete.side_effect = [1, 0]
    fake_client.zrem.return_value = 0
    client = AsyncRedisClient(nodes=["localhost:6379"])
    client.client = fake_client

    await client.cache_set("goals", "g1", {"cached": True}, ttl_seconds=90)
    assert await client.cache_get("goals", "g1") == {"cached": True}
    assert await client.cache_get("goals", "missing") is None
    assert await client.cache_delete("goals", "g1") is True
    assert await client.leaderboard_score("tour-1", "hyp-a") == 1500.0
    assert await client.leaderboard_remove("tour-1", "hyp-a") is False
    assert await client.leaderboard_delete("tour-1") is False

    fake_client.set.assert_awaited_once_with("cache:goals:g1", '{"cached": true}', ex=90)
    fake_client.zrem.assert_awaited_once_with("leaderboard:tour-1", "hyp-a")


@pytest.mark.asyncio
async def test_get_client_initializes_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _build_client()
    client = AsyncRedisClient(nodes=["localhost:6379"])

    async def initialize() -> None:
        client.client = fake_client

    monkeypatch.setattr(client, "initialize", initialize)

    resolved = await client._get_client()

    assert resolved is fake_client


@pytest.mark.asyncio
async def test_eval_script_reloads_script_on_noscript(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _build_client()
    fake_client.evalsha.side_effect = RedisError("NOSCRIPT missing")
    fake_client.eval.return_value = ["fallback"]
    client = AsyncRedisClient(nodes=["localhost:6379"])

    monkeypatch.setattr(
        AsyncRedisClient,
        "_script_source",
        lambda self, script_name: f"return '{script_name}'",
    )

    result = await client._eval_script(fake_client, "budget_decrement.lua", ["budget:k"], [1, 2])

    assert result == ["fallback"]
    fake_client.eval.assert_awaited_once_with("return 'budget_decrement.lua'", 1, "budget:k", 1, 2)


@pytest.mark.asyncio
async def test_eval_script_reraises_non_noscript_errors() -> None:
    fake_client = _build_client()
    fake_client.evalsha.side_effect = RedisError("boom")
    client = AsyncRedisClient(nodes=["localhost:6379"])
    client._lua_scripts["budget_decrement.lua"] = "sha-budget"

    with pytest.raises(RedisError, match="boom"):
        await client._eval_script(fake_client, "budget_decrement.lua", ["budget:k"], [1])


@pytest.mark.asyncio
async def test_get_script_sha_caches_loaded_scripts(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _build_client()
    fake_client.script_load.side_effect = ["sha-1"]
    client = AsyncRedisClient(nodes=["localhost:6379"])

    monkeypatch.setattr(
        AsyncRedisClient,
        "_script_source",
        lambda self, script_name: f"-- {script_name}",
    )

    first = await client._get_script_sha(fake_client, "lock_acquire.lua")
    second = await client._get_script_sha(fake_client, "lock_acquire.lua")

    assert first == "sha-1"
    assert second == "sha-1"
    fake_client.script_load.assert_awaited_once_with("-- lock_acquire.lua")


def test_script_source_and_key_builders_use_expected_paths() -> None:
    source = AsyncRedisClient(nodes=["localhost:6379"])._script_source("budget_decrement.lua")

    assert "remaining_time_ms" in source
    assert AsyncRedisClient._session_key("u1", "s1") == "session:u1:s1"
    assert AsyncRedisClient._budget_key("exec-1", "step-1") == "budget:exec-1:step-1"
    assert AsyncRedisClient._rate_limit_key("workspace", "abc") == "ratelimit:workspace:abc"
    assert AsyncRedisClient._lock_key("workflow", "run-1") == "lock:workflow:run-1"
    assert AsyncRedisClient._leaderboard_key("tour-1") == "leaderboard:tour-1"
    assert AsyncRedisClient._cache_key("goals", "g1") == "cache:goals:g1"


def test_refresh_runtime_config_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AsyncRedisClient(nodes=["localhost:6379"])
    client._standalone = False
    client._url = None

    monkeypatch.setenv("REDIS_TEST_MODE", "standalone")
    monkeypatch.setenv("REDIS_URL", "redis://env-cache:6379")

    client._refresh_runtime_config()

    assert client._standalone is True
    assert client._url == "redis://env-cache:6379"


def test_refresh_runtime_config_keeps_current_values_when_env_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AsyncRedisClient(nodes=["localhost:6379"])
    client._standalone = True
    client._url = "redis://current:6379"

    monkeypatch.delenv("REDIS_TEST_MODE", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    client._refresh_runtime_config()

    assert client._standalone is True
    assert client._url == "redis://current:6379"
