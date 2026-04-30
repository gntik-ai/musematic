from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.two_person_approval.models import ChallengeStatus, TwoPersonApprovalChallenge
from platform.two_person_approval.service import (
    TwoPersonApprovalConflictError,
    TwoPersonApprovalError,
    TwoPersonApprovalNotFoundError,
    TwoPersonApprovalService,
)
from typing import Any
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
        self.added: list[TwoPersonApprovalChallenge] = []
        self.flushes = 0

    def add(self, challenge: TwoPersonApprovalChallenge) -> None:
        self.challenge = challenge
        self.added.append(challenge)

    async def flush(self) -> None:
        self.flushes += 1

    async def execute(self, _statement: object) -> _ScalarResult:
        return _ScalarResult(self.challenge)


class _Redis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, int]] = []

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        self.calls.append((key, value, ttl))


def _challenge(
    *,
    challenge_id: UUID | None = None,
    initiator_id: UUID | None = None,
    expires_at: datetime | None = None,
    approved_at: datetime | None = None,
    co_signer_id: UUID | None = None,
    consumed: bool = False,
) -> TwoPersonApprovalChallenge:
    now = datetime.now(UTC)
    status = ChallengeStatus.pending
    if approved_at is not None:
        status = ChallengeStatus.approved
    if consumed:
        status = ChallengeStatus.consumed
    challenge = TwoPersonApprovalChallenge(
        id=challenge_id or uuid4(),
        action_type="workspace_transfer_ownership",
        action_payload={"workspace_id": str(uuid4())},
        initiator_id=initiator_id or uuid4(),
        status=status,
        created_at=now,
        expires_at=expires_at or now + timedelta(minutes=5),
        consumed_at=now if consumed else None,
    )
    challenge.approved_at = approved_at
    challenge.co_signer_id = co_signer_id
    return challenge


@pytest.mark.asyncio
async def test_challenge_lifecycle_mirrors_and_consumes_payload() -> None:
    session = _Session()
    redis = _Redis()
    service = TwoPersonApprovalService(session, redis)
    initiator_id = uuid4()
    co_signer_id = uuid4()
    action_payload: dict[str, Any] = {"workspace_id": str(uuid4()), "new_owner_id": str(uuid4())}

    created = await service.create_challenge(
        initiator_id=initiator_id,
        action_type="workspace_transfer_ownership",
        action_payload=action_payload,
        ttl_seconds=120,
    )
    approved = await service.approve_challenge(
        challenge_id=created.id,
        co_signer_id=co_signer_id,
    )
    consumed, payload = await service.consume_challenge(
        challenge_id=created.id,
        requester_id=initiator_id,
    )

    assert created.status == "pending"
    assert approved.status == "approved"
    assert consumed.status == "consumed"
    assert consumed.consumed_at is not None
    assert payload == action_payload
    assert session.flushes == 3
    assert len(redis.calls) == 3
    mirrored = json.loads(redis.calls[-1][1].decode("utf-8"))
    assert mirrored["status"] == "consumed"
    assert redis.calls[-1][2] > 0


@pytest.mark.asyncio
async def test_get_challenge_and_not_found_or_expired_errors() -> None:
    session = _Session()
    service = TwoPersonApprovalService(session)
    session.challenge = _challenge()

    fetched = await service.get_challenge(session.challenge.id)

    assert fetched.status == "pending"

    session.challenge = None
    with pytest.raises(TwoPersonApprovalNotFoundError) as not_found:
        await service.get_challenge(uuid4())
    assert not_found.value.code == "TWO_PERSON_APPROVAL_NOT_FOUND"

    session.challenge = _challenge(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(TwoPersonApprovalConflictError) as expired:
        await service.get_challenge(session.challenge.id)
    assert expired.value.code == "TWO_PERSON_APPROVAL_EXPIRED"


@pytest.mark.asyncio
async def test_create_challenge_without_redis_skips_mirror() -> None:
    session = _Session()
    service = TwoPersonApprovalService(session)
    initiator_id = uuid4()

    response = await service.create_challenge(
        initiator_id=initiator_id,
        action_type="workspace_transfer_ownership",
        action_payload={"workspace_id": str(uuid4())},
    )

    assert response.initiator_id == initiator_id
    assert response.status == "pending"
    assert session.flushes == 1


@pytest.mark.asyncio
async def test_approval_and_consumption_reject_invalid_states() -> None:
    session = _Session()
    service = TwoPersonApprovalService(session)
    initiator_id = uuid4()

    session.challenge = None
    with pytest.raises(TwoPersonApprovalNotFoundError):
        await service.approve_challenge(challenge_id=uuid4(), co_signer_id=uuid4())

    session.challenge = _challenge(initiator_id=initiator_id)
    with pytest.raises(TwoPersonApprovalError) as same_actor:
        await service.approve_challenge(
            challenge_id=session.challenge.id,
            co_signer_id=initiator_id,
        )
    assert same_actor.value.code == "TWO_PERSON_APPROVAL_SAME_ACTOR"

    session.challenge = _challenge(
        initiator_id=initiator_id,
        approved_at=datetime.now(UTC),
        co_signer_id=uuid4(),
    )
    with pytest.raises(TwoPersonApprovalConflictError) as not_pending:
        await service.approve_challenge(
            challenge_id=session.challenge.id,
            co_signer_id=uuid4(),
        )
    assert not_pending.value.code == "TWO_PERSON_APPROVAL_NOT_PENDING"

    session.challenge = _challenge(initiator_id=initiator_id)
    with pytest.raises(TwoPersonApprovalError) as wrong_initiator:
        await service.consume_challenge(
            challenge_id=session.challenge.id,
            requester_id=uuid4(),
        )
    assert wrong_initiator.value.code == "TWO_PERSON_APPROVAL_INITIATOR_REQUIRED"

    with pytest.raises(TwoPersonApprovalConflictError) as not_approved:
        await service.consume_challenge(
            challenge_id=session.challenge.id,
            requester_id=initiator_id,
        )
    assert not_approved.value.code == "TWO_PERSON_APPROVAL_NOT_APPROVED"


def test_model_status_values_cover_core_branches() -> None:
    assert _challenge().status == "pending"
    assert _challenge(approved_at=datetime.now(UTC), co_signer_id=uuid4()).status == "approved"
    assert _challenge(consumed=True).status == "consumed"
