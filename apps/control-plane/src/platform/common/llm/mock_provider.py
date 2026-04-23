from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from platform.common.clients.redis import AsyncRedisClient
from typing import Any, ClassVar, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class BaseProvider(Protocol):
    async def generate(
        self,
        prompt_pattern: str,
        prompt: str,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        correlation_context: dict[str, Any] | None = None,
    ) -> str: ...

    async def stream(
        self,
        prompt_pattern: str,
        prompt: str,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        correlation_context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]: ...


class MockLLMCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(default_factory=lambda: str(uuid4()))
    prompt_pattern: str
    prompt: str
    model: str
    temperature: float
    max_tokens: int
    response: str
    from_queue: bool
    streaming: bool
    started_at: str
    duration_ms: int
    correlation_context: dict[str, Any] = Field(default_factory=dict)


class MockLLMProvider:
    DEFAULT_RESPONSES: ClassVar[dict[str, str]] = {
        "agent_response": "Mock agent response",
        "judge_verdict": '{"verdict": "allow"}',
        "tool_selector": '{"tool": "mock-http-tool"}',
    }
    BROADCAST_CHANNEL = "e2e:mock_llm:set"
    CALLS_KEY = "e2e:mock_llm:calls"
    PATTERNS_KEY = "e2e:mock_llm:patterns"
    CALLS_LIMIT = 1000

    def __init__(self, redis_client: AsyncRedisClient | Any) -> None:
        self.redis_client = redis_client

    async def set_response(
        self,
        prompt_pattern: str,
        response: str,
        streaming_chunks: list[str] | None = None,
    ) -> dict[str, int]:
        payload = {
            "prompt_pattern": prompt_pattern,
            "response": response,
            "streaming_chunks": streaming_chunks or [],
        }
        payload_json = json.dumps(payload)
        client = await self._redis()
        queue_key = self._queue_key(prompt_pattern)
        await client.sadd(self.PATTERNS_KEY, prompt_pattern)
        await client.rpush(queue_key, payload_json)
        await self._publish(client, self.BROADCAST_CHANNEL, payload_json)
        return await self.queue_depth()

    async def set_responses(self, responses: dict[str, list[str]]) -> dict[str, int]:
        for prompt_pattern, items in responses.items():
            for response in items:
                await self.set_response(prompt_pattern, response)
        return await self.queue_depth()

    async def queue_depth(self) -> dict[str, int]:
        client = await self._redis()
        patterns = set(await self._patterns(client)) | set(self.DEFAULT_RESPONSES)
        depths: dict[str, int] = {}
        for pattern in sorted(patterns):
            depths[pattern] = int(await client.llen(self._queue_key(pattern)))
        return depths

    async def clear_queue(self, prompt_pattern: str | None = None) -> None:
        client = await self._redis()
        if prompt_pattern is not None:
            await client.delete(self._queue_key(prompt_pattern))
            return
        patterns = await self._patterns(client)
        keys = [self._queue_key(pattern) for pattern in patterns]
        if keys:
            await client.delete(*keys)

    async def get_calls(
        self,
        *,
        pattern: str | None = None,
        since: str | None = None,
    ) -> list[MockLLMCallRecord]:
        client = await self._redis()
        records = [
            MockLLMCallRecord.model_validate_json(item)
            for item in await client.lrange(self.CALLS_KEY, 0, -1)
        ]
        filtered = records
        if pattern is not None:
            filtered = [record for record in filtered if record.prompt_pattern == pattern]
        if since is not None:
            filtered = [record for record in filtered if record.started_at >= since]
        return filtered

    async def generate(
        self,
        prompt_pattern: str,
        prompt: str,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        correlation_context: dict[str, Any] | None = None,
    ) -> str:
        result = await self._dequeue_response(prompt_pattern)
        await self._record_call(
            prompt_pattern=prompt_pattern,
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response=result["response"],
            from_queue=result["from_queue"],
            streaming=False,
            correlation_context=correlation_context,
        )
        return str(result["response"])

    async def stream(
        self,
        prompt_pattern: str,
        prompt: str,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        correlation_context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        result = await self._dequeue_response(prompt_pattern)
        await self._record_call(
            prompt_pattern=prompt_pattern,
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response=result["response"],
            from_queue=result["from_queue"],
            streaming=True,
            correlation_context=correlation_context,
        )
        chunks = result["streaming_chunks"] or [result["response"]]
        for chunk in chunks:
            yield str(chunk)
            await asyncio.sleep(0)

    async def _dequeue_response(self, prompt_pattern: str) -> dict[str, Any]:
        client = await self._redis()
        raw = await client.lpop(self._queue_key(prompt_pattern))
        if raw is None:
            fallback = self.DEFAULT_RESPONSES.get(
                prompt_pattern,
                f"Mock response for {prompt_pattern}",
            )
            return {
                "response": fallback,
                "streaming_chunks": [],
                "from_queue": False,
            }
        payload = json.loads(raw)
        return {
            "response": str(payload["response"]),
            "streaming_chunks": [
                str(item) for item in payload.get("streaming_chunks", [])
            ],
            "from_queue": True,
        }

    async def _record_call(
        self,
        *,
        prompt_pattern: str,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
        response: str,
        from_queue: bool,
        streaming: bool,
        correlation_context: dict[str, Any] | None,
    ) -> None:
        client = await self._redis()
        record = MockLLMCallRecord(
            prompt_pattern=prompt_pattern,
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response=response,
            from_queue=from_queue,
            streaming=streaming,
            started_at=datetime.now(UTC).isoformat(),
            duration_ms=0,
            correlation_context=correlation_context or {},
        )
        await client.rpush(self.CALLS_KEY, record.model_dump_json())
        await client.ltrim(self.CALLS_KEY, -self.CALLS_LIMIT, -1)

    async def _redis(self) -> Any:
        get_client = getattr(self.redis_client, "_get_client", None)
        if callable(get_client):
            return await get_client()
        return self.redis_client

    async def _patterns(self, client: Any) -> list[str]:
        values = await client.smembers(self.PATTERNS_KEY)
        if not values:
            return []
        return sorted(str(value) for value in values)

    async def _publish(self, client: Any, channel: str, payload: str) -> None:
        publish = getattr(client, "publish", None)
        if callable(publish):
            await publish(channel, payload)
            return
        execute_command = getattr(client, "execute_command", None)
        if callable(execute_command):
            await execute_command("PUBLISH", channel, payload)
            return
        raise AttributeError("Redis client does not support publish semantics")

    @staticmethod
    def _queue_key(prompt_pattern: str) -> str:
        return f"e2e:mock_llm:queue:{prompt_pattern}"
