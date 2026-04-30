from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.two_person_approval.models import TwoPersonApprovalChallenge
from platform.two_person_approval.service import (
    TwoPersonApprovalConflictError,
    TwoPersonApprovalError,
    TwoPersonApprovalService,
)
from uuid import UUID, uuid4

import pytest


class _ScalarResult:
    def __init__(self, challenge: TwoPersonApprovalChallenge | None) -> None:
        self.challenge = challenge

    def scalar_one_or_none(self) -> TwoPersonApprovalChallenge | None:
        return self.challenge


class _Session:
    def __init__(self) -> None:
        self.challenge: TwoPersonApprovalChallenge | None = None
        self.flushes = 0

    def add(self, challenge: TwoPersonApprovalChallenge) -> None:
        self.challenge = challenge

    async def flush(self) -> None:
        self.flushes += 1

    async def execute(self, _statement: object) -> _ScalarResult:
        return _ScalarResult(self.challenge)


class _Redis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        self.values[key] = value
        self.ttls[key] = ttl


def _challenge(
    *,
    initiator_id: UUID | None = None,
    approved: bool = False,
    consumed: bool = False,
    expires_at: datetime | None = None,
) -> TwoPersonApprovalChallenge:
    now = datetime.now(UTC)
    challenge = TwoPersonApprovalChallenge(
        id=uuid4(),
        action_type="workspace_transfer_ownership",
        action_payload={"workspace_id": str(uuid4()), "new_owner_id": str(uuid4())},
        initiator_id=initiator_id or uuid4(),
        created_at=now,
        expires_at=expires_at or now + timedelta(minutes=5),
        consumed=consumed,
    )
    if approved:
        challenge.approved_at = now
        challenge.co_signer_id = uuid4()
    return challenge


@pytest.mark.asyncio
async def test_create_approve_consume_uses_frozen_payload_and_redis_ttl() -> None:
    session = _Session()
    redis = _Redis()
    service = TwoPersonApprovalService(session, redis)
    initiator_id = uuid4()
    payload = {"workspace_id": str(uuid4()), "new_owner_id": str(uuid4())}

    created = await service.create_challenge(
        initiator_id=initiator_id,
        action_type="workspace_transfer_ownership",
        action_payload=payload,
        ttl_seconds=120,
    )
    approved = await service.approve_challenge(challenge_id=created.id, co_signer_id=uuid4())
    consumed, consumed_payload = await service.consume_challenge(
        challenge_id=created.id,
        requester_id=initiator_id,
    )

    assert created.status == "pending"
    assert approved.status == "approved"
    assert consumed.status == "consumed"
    assert consumed_payload == payload
    assert session.flushes == 3

    mirror = json.loads(redis.values[f"2pa:challenge:{created.id}"].decode("utf-8"))
    assert mirror["status"] == "consumed"
    assert redis.ttls[f"2pa:challenge:{created.id}"] > 0


@pytest.mark.asyncio
async def test_same_actor_expired_and_double_consume_are_rejected() -> None:
    session = _Session()
    service = TwoPersonApprovalService(session)
    initiator_id = uuid4()

    session.challenge = _challenge(initiator_id=initiator_id)
    with pytest.raises(TwoPersonApprovalError) as same_actor:
        await service.approve_challenge(
            challenge_id=session.challenge.id,
            co_signer_id=initiator_id,
        )
    assert same_actor.value.code == "TWO_PERSON_APPROVAL_SAME_ACTOR"

    session.challenge = _challenge(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(TwoPersonApprovalConflictError) as expired:
        await service.get_challenge(session.challenge.id)
    assert expired.value.code == "TWO_PERSON_APPROVAL_EXPIRED"

    session.challenge = _challenge(initiator_id=initiator_id, approved=True)
    await service.consume_challenge(challenge_id=session.challenge.id, requester_id=initiator_id)
    with pytest.raises(TwoPersonApprovalConflictError) as double_consume:
        await service.consume_challenge(
            challenge_id=session.challenge.id,
            requester_id=initiator_id,
        )
    assert double_consume.value.code == "TWO_PERSON_APPROVAL_NOT_APPROVED"
