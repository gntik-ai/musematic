from __future__ import annotations

from collections.abc import Iterable, Mapping
from platform.privacy_compliance.redis_keys import TRAINING_REVOKED_USERS_KEY
from typing import Any


class TrainingCorpusComposer:
    """Compose training corpora while honoring consent revocations."""

    def __init__(self, redis_client: object | None = None) -> None:
        self.redis = redis_client

    async def compose(
        self,
        messages: Iterable[Mapping[str, Any]],
        *,
        snapshot_revoked_user_ids: Iterable[str] | None = None,
    ) -> list[Mapping[str, Any]]:
        revoked = (
            set(snapshot_revoked_user_ids)
            if snapshot_revoked_user_ids is not None
            else await snapshot_revoked_training_users(self.redis)
        )
        if not revoked:
            return list(messages)
        return [
            message
            for message in messages
            if _message_user_id(message) not in revoked
        ]


async def snapshot_revoked_training_users(redis_client: object | None) -> set[str]:
    """Return a point-in-time revoked-user snapshot for training jobs."""

    if redis_client is None:
        return set()
    smembers = getattr(redis_client, "smembers", None)
    if not callable(smembers):
        getter = getattr(redis_client, "_get_client", None)
        if callable(getter):
            client = await getter()
            smembers = getattr(client, "smembers", None)
    if not callable(smembers):
        return set()
    raw_values = smembers(TRAINING_REVOKED_USERS_KEY)
    if hasattr(raw_values, "__await__"):
        raw_values = await raw_values
    return {_decode_redis_member(value) for value in raw_values or set()}


def _message_user_id(message: Mapping[str, Any]) -> str | None:
    for key in ("user_id", "subject_user_id", "principal_id", "created_by"):
        value = message.get(key)
        if value is not None:
            return str(value)
    return None


def _decode_redis_member(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
