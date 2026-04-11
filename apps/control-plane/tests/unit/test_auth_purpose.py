from __future__ import annotations

from platform.auth.purpose import check_purpose_bound
from platform.common.exceptions import PolicyViolationError
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer


@pytest.mark.asyncio
async def test_check_purpose_bound_skips_non_agent() -> None:
    producer = RecordingProducer()

    await check_purpose_bound(
        "user",
        "data-analysis",
        "analytics",
        "read",
        producer,
        uuid4(),
        identity_id=uuid4(),
    )

    assert producer.events == []


@pytest.mark.asyncio
async def test_check_purpose_bound_allows_aligned_action() -> None:
    producer = RecordingProducer()

    await check_purpose_bound(
        "agent",
        "retrieval",
        "memory",
        "read",
        producer,
        uuid4(),
        identity_id=uuid4(),
    )

    assert producer.events == []


@pytest.mark.asyncio
async def test_check_purpose_bound_denies_out_of_scope_action() -> None:
    producer = RecordingProducer()
    identity_id = uuid4()

    with pytest.raises(PolicyViolationError):
        await check_purpose_bound(
            "agent",
            "data-analysis",
            "agent",
            "delete",
            producer,
            uuid4(),
            identity_id=identity_id,
        )

    assert producer.events[0]["event_type"] == "auth.permission.denied"
    assert producer.events[0]["payload"]["user_id"] == str(identity_id)
    assert producer.events[0]["payload"]["reason"] == "purpose_violation"
