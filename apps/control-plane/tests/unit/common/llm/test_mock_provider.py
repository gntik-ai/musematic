from __future__ import annotations

from platform.common.llm.mock_provider import MockLLMProvider

import pytest


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.sets: dict[str, set[str]] = {}
        self.published: list[tuple[str, str]] = []

    async def sadd(self, key: str, *values: str) -> None:
        self.sets.setdefault(key, set()).update(values)

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))

    async def rpush(self, key: str, *values: str) -> int:
        bucket = self.lists.setdefault(key, [])
        bucket.extend(values)
        return len(bucket)

    async def lpush(self, key: str, *values: str) -> int:
        bucket = self.lists.setdefault(key, [])
        for value in reversed(values):
            bucket.insert(0, value)
        return len(bucket)

    async def lpop(self, key: str):
        bucket = self.lists.get(key, [])
        if not bucket:
            return None
        return bucket.pop(0)

    async def lrange(self, key: str, start: int, end: int):
        bucket = self.lists.get(key, [])
        if end == -1:
            return list(bucket[start:])
        return list(bucket[start : end + 1])

    async def ltrim(self, key: str, start: int, end: int) -> None:
        bucket = self.lists.get(key, [])
        if end == -1:
            self.lists[key] = bucket[start:]
        else:
            self.lists[key] = bucket[start : end + 1]

    async def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    async def publish(self, channel: str, payload: str) -> None:
        self.published.append((channel, payload))

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            deleted += int(key in self.lists or key in self.sets)
            self.lists.pop(key, None)
            self.sets.pop(key, None)
        return deleted


class FakeRedisCluster(FakeRedis):
    publish = None

    async def execute_command(self, command: str, channel: str, payload: str) -> int:
        assert command == 'PUBLISH'
        self.published.append((channel, payload))
        return 1




@pytest.mark.asyncio
async def test_mock_provider_broadcasts_with_execute_command_when_publish_is_unavailable() -> None:
    redis = FakeRedisCluster()
    provider = MockLLMProvider(redis)

    await provider.set_response('agent_response', 'cluster-safe')

    expected_payload = (
        '{"prompt_pattern": "agent_response", '
        '"response": "cluster-safe", '
        '"streaming_chunks": []}'
    )

    assert redis.published == [
        (
            provider.BROADCAST_CHANNEL,
            expected_payload,
        )
    ]


@pytest.mark.asyncio
async def test_mock_provider_returns_fifo_responses_and_records_calls() -> None:
    redis = FakeRedis()
    provider = MockLLMProvider(redis)

    await provider.set_response('agent_response', 'first')
    await provider.set_response('agent_response', 'second')

    assert await provider.generate(
        'agent_response',
        'prompt-1',
        model='mock',
        temperature=0.1,
        max_tokens=10,
    ) == 'first'
    assert await provider.generate(
        'agent_response',
        'prompt-2',
        model='mock',
        temperature=0.1,
        max_tokens=10,
    ) == 'second'

    calls = await provider.get_calls(pattern='agent_response')
    assert [call.response for call in calls] == ['first', 'second']
    assert all(call.from_queue for call in calls)


@pytest.mark.asyncio
async def test_mock_provider_uses_fallback_and_streaming_chunks() -> None:
    redis = FakeRedis()
    provider = MockLLMProvider(redis)

    fallback = await provider.generate(
        'judge_verdict',
        'prompt-fallback',
        model='mock',
        temperature=0,
        max_tokens=5,
    )
    assert fallback == '{"verdict": "allow"}'

    await provider.set_response('agent_response', 'chunked', ['ch', 'unk', 'ed'])
    chunks = [
        chunk
        async for chunk in provider.stream(
            'agent_response',
            'prompt-stream',
            model='mock',
            temperature=0,
            max_tokens=5,
        )
    ]
    assert chunks == ['ch', 'unk', 'ed']

    calls = await provider.get_calls()
    assert calls[0].from_queue is False
    assert calls[1].streaming is True


@pytest.mark.asyncio
async def test_mock_provider_tracks_queue_depth_and_broadcasts_updates() -> None:
    redis = FakeRedis()
    provider = MockLLMProvider(redis)

    await provider.set_responses({'agent_response': ['one', 'two']})
    depth = await provider.queue_depth()

    assert depth['agent_response'] == 2
    assert redis.published

    await provider.clear_queue()
    cleared = await provider.queue_depth()
    assert cleared['agent_response'] == 0
