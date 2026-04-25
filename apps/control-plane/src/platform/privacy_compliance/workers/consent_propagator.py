from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.privacy_compliance.models import ConsentType
from platform.privacy_compliance.redis_keys import (
    DATA_COLLECTION_DISABLED_USERS_KEY,
    TRAINING_REVOKED_USERS_KEY,
)
from platform.privacy_compliance.repository import PrivacyComplianceRepository


class ConsentPropagator:
    def __init__(
        self,
        repository: PrivacyComplianceRepository,
        redis_client: object | None,
    ) -> None:
        self.repository = repository
        self.redis = redis_client

    async def run_once(self) -> int:
        since = datetime.now(UTC) - timedelta(minutes=2)
        revocations = await self.repository.list_recent_revocations(since)
        count = 0
        sadd = getattr(self.redis, "sadd", None)
        for record in revocations:
            key = _redis_key_for_revocation(record.consent_type)
            if key is None:
                continue
            if callable(sadd):
                await sadd(key, str(record.user_id))
            count += 1
        return count


def _redis_key_for_revocation(consent_type: str) -> str | None:
    if consent_type == ConsentType.training_use.value:
        return TRAINING_REVOKED_USERS_KEY
    if consent_type == ConsentType.data_collection.value:
        return DATA_COLLECTION_DISABLED_USERS_KEY
    return None
