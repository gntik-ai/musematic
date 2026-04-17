from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass
from pathlib import Path
from platform.common.config import PlatformSettings
from typing import Any, cast

from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster
from redis.exceptions import RedisError

LUA_DIR = Path(__file__).resolve().parents[6] / "lua"


@dataclass(slots=True)
class BudgetConfig:
    max_tokens: int
    max_rounds: int
    max_cost: float
    max_time_ms: int


@dataclass(slots=True)
class BudgetResult:
    allowed: bool
    remaining_tokens: int
    remaining_rounds: int
    remaining_cost: float
    remaining_time_ms: int


@dataclass(slots=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_ms: int


@dataclass(slots=True)
class LockResult:
    success: bool
    token: str | None = None


class AsyncRedisClient:
    def __init__(self, nodes: list[str], password: str | None = None) -> None:
        self.nodes = nodes
        self.password = password or os.environ.get("REDIS_PASSWORD")
        self._init_lock = asyncio.Lock()
        self._lua_scripts: dict[str, str] = {}
        self.client: Redis | RedisCluster | None = None
        self._standalone = os.environ.get("REDIS_TEST_MODE") == "standalone"
        self._url = os.environ.get("REDIS_URL")

    @classmethod
    def from_settings(cls, settings: PlatformSettings) -> AsyncRedisClient:
        nodes = settings.REDIS_NODES or [settings.REDIS_URL.removeprefix("redis://")]
        client = cls(nodes=nodes, password=settings.REDIS_PASSWORD or None)
        client._standalone = settings.REDIS_TEST_MODE == "standalone"
        client._url = settings.REDIS_URL
        return client

    async def initialize(self) -> None:
        if self._current_client() is not None:
            return

        async with self._init_lock:
            if self._current_client() is not None:
                return

            self._refresh_runtime_config()

            if self._standalone:
                if self._url:
                    self.client = Redis.from_url(self._url, decode_responses=True)
                else:
                    host, port = self.nodes[0].split(":", 1)
                    self.client = Redis(
                        host=host,
                        port=int(port),
                        password=self.password,
                        decode_responses=True,
                    )
            else:
                bootstrap_url = self._url
                if bootstrap_url is None:
                    bootstrap_url = f"redis://:{self.password or ''}@{self.nodes[0]}"
                self.client = RedisCluster.from_url(
                    bootstrap_url,
                    password=self.password,
                    max_connections=32,
                    decode_responses=True,
                    require_full_coverage=False,
                )

            for script_name in (
                "budget_decrement.lua",
                "rate_limit_check.lua",
                "lock_acquire.lua",
                "lock_release.lua",
            ):
                await self._get_script_sha(self.client, script_name)

    async def close(self) -> None:
        if self.client is None:
            return
        aclose = getattr(self.client, "aclose", None)
        if callable(aclose):
            await aclose()
        else:
            await self.client.close()
        self.client = None

    async def connect(self) -> None:
        await self.initialize()

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            response = client.ping()
            if hasattr(response, "__await__"):
                response = await cast(Awaitable[Any], response)
            return bool(response)
        except RedisError:
            return False

    async def get(self, key: str) -> bytes | None:
        client = await self._get_client()
        value = await client.get(key)
        if value is None:
            return None
        if isinstance(value, bytes):
            return value
        return str(value).encode()

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        client = await self._get_client()
        await client.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        client = await self._get_client()
        await client.delete(key)

    async def hgetall(self, key: str) -> dict[Any, Any]:
        client = await self._get_client()
        return cast(dict[Any, Any], await cast(Any, client.hgetall(key)))

    async def evalsha(self, sha: str, keys: list[Any], args: list[Any]) -> Any:
        client = await self._get_client()
        return await cast(Any, client.evalsha(sha, len(keys), *keys, *args))

    async def set_session(
        self,
        user_id: str,
        session_id: str,
        data: dict[str, Any],
        ttl_seconds: int = 1800,
    ) -> None:
        client = await self._get_client()
        await client.set(self._session_key(user_id, session_id), json.dumps(data), ex=ttl_seconds)

    async def get_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        client = await self._get_client()
        value = await client.get(self._session_key(user_id, session_id))
        return None if value is None else json.loads(value)

    async def delete_session(self, user_id: str, session_id: str) -> bool:
        client = await self._get_client()
        deleted = await client.delete(self._session_key(user_id, session_id))
        return bool(deleted)

    async def invalidate_user_sessions(self, user_id: str) -> int:
        client = await self._get_client()
        pattern = self._session_key(user_id, "*")
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                deleted += int(await client.delete(*keys))
            if cursor == 0:
                break
        return deleted

    async def init_budget(
        self,
        execution_id: str,
        step_id: str,
        config: BudgetConfig,
        ttl_seconds: int,
    ) -> None:
        client = await self._get_client()
        key = self._budget_key(execution_id, step_id)
        now_ms = int(time.time() * 1000)
        mapping = {
            "max_tokens": config.max_tokens,
            "used_tokens": 0,
            "max_rounds": config.max_rounds,
            "used_rounds": 0,
            "max_cost": config.max_cost,
            "used_cost": 0,
            "max_time_ms": config.max_time_ms,
            "start_time": now_ms,
        }
        await cast(Any, client.hset(key, mapping=mapping))
        await client.expire(key, ttl_seconds)

    async def decrement_budget(
        self,
        execution_id: str,
        step_id: str,
        dimension: str,
        amount: float,
    ) -> BudgetResult:
        client = await self._get_client()
        key = self._budget_key(execution_id, step_id)
        now_ms = int(time.time() * 1000)
        result = await self._eval_script(
            client,
            "budget_decrement.lua",
            [key],
            [now_ms, dimension, amount],
        )
        return BudgetResult(
            allowed=bool(int(result[0])),
            remaining_tokens=int(float(result[1])),
            remaining_rounds=int(float(result[2])),
            remaining_cost=float(result[3]),
            remaining_time_ms=int(float(result[4])),
        )

    async def get_budget(self, execution_id: str, step_id: str) -> dict[str, Any] | None:
        client = await self._get_client()
        data = await cast(Any, client.hgetall(self._budget_key(execution_id, step_id)))
        return data or None

    async def delete_budget(self, execution_id: str, step_id: str) -> bool:
        client = await self._get_client()
        deleted = await client.delete(self._budget_key(execution_id, step_id))
        return bool(deleted)

    async def check_rate_limit(
        self,
        resource: str,
        key: str,
        limit: int,
        window_ms: int,
    ) -> RateLimitResult:
        client = await self._get_client()
        result = await self._eval_script(
            client,
            "rate_limit_check.lua",
            [self._rate_limit_key(resource, key)],
            [int(time.time() * 1000), window_ms, limit],
        )
        return RateLimitResult(
            allowed=bool(int(result[0])),
            remaining=int(result[1]),
            retry_after_ms=int(result[2]),
        )

    async def acquire_lock(self, resource: str, id: str, ttl_seconds: int = 10) -> LockResult:
        client = await self._get_client()
        token = str(uuid.uuid4())
        acquired = await self._eval_script(
            client,
            "lock_acquire.lua",
            [self._lock_key(resource, id)],
            [token, ttl_seconds],
        )
        success = bool(int(acquired))
        return LockResult(success=success, token=token if success else None)

    async def release_lock(self, resource: str, id: str, token: str) -> bool:
        client = await self._get_client()
        released = await self._eval_script(
            client,
            "lock_release.lua",
            [self._lock_key(resource, id)],
            [token],
        )
        return bool(int(released))

    async def leaderboard_add(self, tournament_id: str, hypothesis_id: str, score: float) -> None:
        client = await self._get_client()
        await client.zadd(self._leaderboard_key(tournament_id), {hypothesis_id: score})

    async def leaderboard_top(self, tournament_id: str, n: int) -> list[tuple[str, float]]:
        client = await self._get_client()
        entries = await client.zrevrange(
            self._leaderboard_key(tournament_id),
            0,
            max(n - 1, 0),
            withscores=True,
        )
        return [(member, float(score)) for member, score in entries]

    async def leaderboard_rank(self, tournament_id: str, hypothesis_id: str) -> int | None:
        client = await self._get_client()
        rank = await client.zrevrank(self._leaderboard_key(tournament_id), hypothesis_id)
        return cast(int | None, rank)

    async def leaderboard_score(self, tournament_id: str, hypothesis_id: str) -> float | None:
        client = await self._get_client()
        score = await client.zscore(self._leaderboard_key(tournament_id), hypothesis_id)
        return None if score is None else float(score)

    async def leaderboard_remove(self, tournament_id: str, hypothesis_id: str) -> bool:
        client = await self._get_client()
        removed = await client.zrem(self._leaderboard_key(tournament_id), hypothesis_id)
        return bool(removed)

    async def leaderboard_delete(self, tournament_id: str) -> bool:
        client = await self._get_client()
        deleted = await client.delete(self._leaderboard_key(tournament_id))
        return bool(deleted)

    async def cache_set(
        self,
        context: str,
        key: str,
        value: dict[str, Any],
        ttl_seconds: int = 300,
    ) -> None:
        client = await self._get_client()
        await client.set(self._cache_key(context, key), json.dumps(value), ex=ttl_seconds)

    async def cache_get(self, context: str, key: str) -> dict[str, Any] | None:
        client = await self._get_client()
        value = await client.get(self._cache_key(context, key))
        return None if value is None else json.loads(value)

    async def cache_delete(self, context: str, key: str) -> bool:
        client = await self._get_client()
        deleted = await client.delete(self._cache_key(context, key))
        return bool(deleted)

    async def _get_client(self) -> Redis | RedisCluster:
        await self.initialize()
        assert self.client is not None
        return self.client

    def _current_client(self) -> Redis | RedisCluster | None:
        return self.client

    def _refresh_runtime_config(self) -> None:
        test_mode = os.environ.get("REDIS_TEST_MODE")
        if test_mode is not None:
            self._standalone = test_mode == "standalone"

        redis_url = os.environ.get("REDIS_URL")
        if redis_url is not None:
            self._url = redis_url

    async def _eval_script(
        self,
        client: Redis | RedisCluster,
        script_name: str,
        keys: list[str],
        args: list[Any],
    ) -> Any:
        sha = await self._get_script_sha(client, script_name)
        try:
            return await cast(Any, client.evalsha(sha, len(keys), *keys, *args))
        except RedisError as exc:
            if "NOSCRIPT" not in str(exc):
                raise
            self._lua_scripts.pop(script_name, None)
            source = self._script_source(script_name)
            return await cast(Any, client.eval(source, len(keys), *keys, *args))

    async def _get_script_sha(self, client: Redis | RedisCluster, script_name: str) -> str:
        sha = self._lua_scripts.get(script_name)
        if sha is not None:
            return sha
        source = self._script_source(script_name)
        sha = cast(str, await cast(Any, client.script_load(source)))
        self._lua_scripts[script_name] = sha
        return sha

    def _script_source(self, script_name: str) -> str:
        return (LUA_DIR / script_name).read_text(encoding="utf-8")

    @staticmethod
    def _session_key(user_id: str, session_id: str) -> str:
        return f"session:{user_id}:{session_id}"

    @staticmethod
    def _budget_key(execution_id: str, step_id: str) -> str:
        return f"budget:{execution_id}:{step_id}"

    @staticmethod
    def _rate_limit_key(resource: str, key: str) -> str:
        return f"ratelimit:{resource}:{key}"

    @staticmethod
    def _lock_key(resource: str, id: str) -> str:
        return f"lock:{resource}:{id}"

    @staticmethod
    def _leaderboard_key(tournament_id: str) -> str:
        return f"leaderboard:{tournament_id}"

    @staticmethod
    def _cache_key(context: str, key: str) -> str:
        return f"cache:{context}:{key}"
