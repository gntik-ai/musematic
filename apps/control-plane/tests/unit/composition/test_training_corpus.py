from __future__ import annotations

from platform.composition.training_corpus import (
    TrainingCorpusComposer,
    snapshot_revoked_training_users,
)
from platform.privacy_compliance.redis_keys import TRAINING_REVOKED_USERS_KEY
from uuid import uuid4

import pytest


class RedisStub:
    def __init__(self) -> None:
        self.sets: dict[str, set[bytes]] = {}

    async def sadd(self, key: str, value: str) -> None:
        self.sets.setdefault(key, set()).add(value.encode("utf-8"))

    async def smembers(self, key: str) -> set[bytes]:
        return set(self.sets.get(key, set()))


class WrappedRedisStub:
    def __init__(self, client: RedisStub) -> None:
        self.client = client

    async def _get_client(self) -> RedisStub:
        return self.client


@pytest.mark.asyncio
async def test_training_corpus_excludes_revoked_training_users() -> None:
    revoked_user = uuid4()
    allowed_user = uuid4()
    redis = RedisStub()
    await redis.sadd(TRAINING_REVOKED_USERS_KEY, str(revoked_user))
    composer = TrainingCorpusComposer(redis)

    corpus = await composer.compose(
        [
            {"user_id": str(revoked_user), "text": "must not train"},
            {"user_id": str(allowed_user), "text": "allowed"},
        ]
    )

    assert corpus == [{"user_id": str(allowed_user), "text": "allowed"}]


@pytest.mark.asyncio
async def test_training_corpus_snapshot_isolation_allows_in_flight_jobs() -> None:
    revoked_after_snapshot = uuid4()
    redis = RedisStub()
    composer = TrainingCorpusComposer(redis)
    snapshot = await snapshot_revoked_training_users(redis)
    await redis.sadd(TRAINING_REVOKED_USERS_KEY, str(revoked_after_snapshot))

    corpus = await composer.compose(
        [{"user_id": str(revoked_after_snapshot), "text": "already snapshotted"}],
        snapshot_revoked_user_ids=snapshot,
    )
    post_revocation_corpus = await composer.compose(
        [{"user_id": str(revoked_after_snapshot), "text": "new job"}]
    )

    assert corpus == [{"user_id": str(revoked_after_snapshot), "text": "already snapshotted"}]
    assert post_revocation_corpus == []


@pytest.mark.asyncio
async def test_training_corpus_handles_missing_and_wrapped_redis_clients() -> None:
    revoked_user = uuid4()
    redis = RedisStub()
    await redis.sadd(TRAINING_REVOKED_USERS_KEY, str(revoked_user))

    assert await snapshot_revoked_training_users(None) == set()
    assert await snapshot_revoked_training_users(object()) == set()
    assert await snapshot_revoked_training_users(WrappedRedisStub(redis)) == {str(revoked_user)}

    composer = TrainingCorpusComposer(redis)
    corpus = await composer.compose(
        [
            {"subject_user_id": str(revoked_user), "text": "subject filtered"},
            {"principal_id": "allowed-principal", "text": "principal allowed"},
            {"created_by": "allowed-creator", "text": "creator allowed"},
            {"text": "anonymous allowed"},
        ],
        snapshot_revoked_user_ids={str(revoked_user)},
    )

    assert corpus == [
        {"principal_id": "allowed-principal", "text": "principal allowed"},
        {"created_by": "allowed-creator", "text": "creator allowed"},
        {"text": "anonymous allowed"},
    ]
