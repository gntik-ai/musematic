from __future__ import annotations

from datetime import UTC, datetime
from platform.composition.training_corpus import TrainingCorpusComposer
from platform.privacy_compliance.models import ConsentType
from platform.privacy_compliance.redis_keys import TRAINING_REVOKED_USERS_KEY
from platform.privacy_compliance.workers.consent_propagator import ConsentPropagator
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


class Repo:
    def __init__(self, user_id) -> None:
        self.user_id = user_id

    async def list_recent_revocations(self, since):
        assert since <= datetime.now(UTC)
        return [
            SimpleNamespace(
                user_id=self.user_id,
                consent_type=ConsentType.training_use.value,
            )
        ]


class RedisStub:
    def __init__(self) -> None:
        self.sets: dict[str, set[str]] = {}

    async def sadd(self, key: str, value: str) -> None:
        self.sets.setdefault(key, set()).add(value)

    async def smembers(self, key: str) -> set[str]:
        return set(self.sets.get(key, set()))


@pytest.mark.asyncio
async def test_consent_revocation_propagates_to_training_corpus_exclusion() -> None:
    revoked_user = uuid4()
    allowed_user = uuid4()
    redis = RedisStub()
    propagator = ConsentPropagator(Repo(revoked_user), redis)

    propagated = await propagator.run_once()
    corpus = await TrainingCorpusComposer(redis).compose(
        [
            {"user_id": str(revoked_user), "text": "exclude me"},
            {"user_id": str(allowed_user), "text": "use me"},
        ]
    )

    assert propagated == 1
    assert redis.sets[TRAINING_REVOKED_USERS_KEY] == {str(revoked_user)}
    assert corpus == [{"user_id": str(allowed_user), "text": "use me"}]
