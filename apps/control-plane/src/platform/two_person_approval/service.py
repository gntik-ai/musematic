from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from platform.common.exceptions import PlatformError
from platform.two_person_approval.models import (
    ActionType,
    ChallengeStatus,
    TwoPersonApprovalChallenge,
)
from platform.two_person_approval.schemas import ChallengeResponse
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TwoPersonApprovalError(PlatformError):
    status_code = 400


class TwoPersonApprovalNotFoundError(TwoPersonApprovalError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("TWO_PERSON_APPROVAL_NOT_FOUND", "2PA challenge not found")


class TwoPersonApprovalConflictError(TwoPersonApprovalError):
    status_code = 409


def _status_value(status: ChallengeStatus | str | None) -> str:
    if isinstance(status, ChallengeStatus):
        return status.value
    return status or ChallengeStatus.pending.value


def _action_type_value(action_type: ActionType | str) -> str:
    if isinstance(action_type, ActionType):
        return action_type.value
    return action_type


class TwoPersonApprovalService:
    def __init__(self, session: AsyncSession, redis_client: Any | None = None) -> None:
        self.session = session
        self.redis_client = redis_client

    async def create_challenge(
        self,
        *,
        initiator_id: UUID,
        action_type: str,
        action_payload: dict[str, Any],
        ttl_seconds: int = 300,
    ) -> ChallengeResponse:
        now = datetime.now(UTC)
        try:
            resolved_action_type = ActionType(action_type)
        except ValueError as exc:
            raise TwoPersonApprovalError(
                "TWO_PERSON_APPROVAL_UNSUPPORTED_ACTION",
                "Unsupported 2PA action type",
            ) from exc

        challenge = TwoPersonApprovalChallenge(
            id=uuid4(),
            action_type=resolved_action_type,
            action_payload=dict(action_payload),
            initiator_id=initiator_id,
            status=ChallengeStatus.pending,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        self.session.add(challenge)
        await self.session.flush()
        await self._mirror(challenge)
        return self._response(challenge)

    async def get_challenge(self, challenge_id: UUID) -> ChallengeResponse:
        challenge = await self._get_or_raise(challenge_id)
        self._raise_if_expired(challenge)
        return self._response(challenge)

    async def approve_challenge(
        self,
        *,
        challenge_id: UUID,
        co_signer_id: UUID,
    ) -> ChallengeResponse:
        challenge = await self._get_for_update_or_raise(challenge_id)
        self._raise_if_expired(challenge)
        if challenge.initiator_id == co_signer_id:
            raise TwoPersonApprovalError(
                "TWO_PERSON_APPROVAL_SAME_ACTOR",
                "The co-signer must be a different user",
            )
        if _status_value(challenge.status) != ChallengeStatus.pending.value:
            raise TwoPersonApprovalConflictError(
                "TWO_PERSON_APPROVAL_NOT_PENDING",
                "Only pending 2PA challenges can be approved",
            )
        now = datetime.now(UTC)
        challenge.co_signer_id = co_signer_id
        challenge.status = ChallengeStatus.approved
        challenge.approved_at = now
        await self.session.flush()
        await self._mirror(challenge)
        return self._response(challenge)

    async def consume_challenge(
        self,
        *,
        challenge_id: UUID,
        requester_id: UUID,
    ) -> tuple[ChallengeResponse, dict[str, Any]]:
        challenge = await self._get_for_update_or_raise(challenge_id)
        self._raise_if_expired(challenge)
        if challenge.initiator_id != requester_id:
            raise TwoPersonApprovalError(
                "TWO_PERSON_APPROVAL_INITIATOR_REQUIRED",
                "Only the original initiator can consume this 2PA challenge",
            )
        if _status_value(challenge.status) != ChallengeStatus.approved.value:
            raise TwoPersonApprovalConflictError(
                "TWO_PERSON_APPROVAL_NOT_APPROVED",
                "Only approved 2PA challenges can be consumed",
            )
        payload = dict(challenge.action_payload)
        now = datetime.now(UTC)
        challenge.status = ChallengeStatus.consumed
        challenge.consumed_at = now
        await self.session.flush()
        await self._mirror(challenge)
        return self._response(challenge), payload

    async def _get_or_raise(self, challenge_id: UUID) -> TwoPersonApprovalChallenge:
        result = await self.session.execute(
            select(TwoPersonApprovalChallenge).where(TwoPersonApprovalChallenge.id == challenge_id)
        )
        challenge = result.scalar_one_or_none()
        if challenge is None:
            raise TwoPersonApprovalNotFoundError()
        return challenge

    async def _get_for_update_or_raise(self, challenge_id: UUID) -> TwoPersonApprovalChallenge:
        result = await self.session.execute(
            select(TwoPersonApprovalChallenge)
            .where(TwoPersonApprovalChallenge.id == challenge_id)
            .with_for_update()
        )
        challenge = result.scalar_one_or_none()
        if challenge is None:
            raise TwoPersonApprovalNotFoundError()
        return challenge

    @staticmethod
    def _raise_if_expired(challenge: TwoPersonApprovalChallenge) -> None:
        if challenge.expires_at <= datetime.now(UTC):
            raise TwoPersonApprovalConflictError(
                "TWO_PERSON_APPROVAL_EXPIRED",
                "2PA challenge has expired",
            )

    async def _mirror(self, challenge: TwoPersonApprovalChallenge) -> None:
        if self.redis_client is None:
            return
        ttl = max(1, int((challenge.expires_at - datetime.now(UTC)).total_seconds()))
        payload = {
            "id": str(challenge.id),
            "action_type": _action_type_value(challenge.action_type),
            "status": _status_value(challenge.status),
            "initiator_id": str(challenge.initiator_id),
            "co_signer_id": str(challenge.co_signer_id) if challenge.co_signer_id else None,
            "expires_at": challenge.expires_at.isoformat(),
        }
        await self.redis_client.set(
            f"2pa:challenge:{challenge.id}",
            json.dumps(payload).encode("utf-8"),
            ttl=ttl,
        )

    @staticmethod
    def _response(challenge: TwoPersonApprovalChallenge) -> ChallengeResponse:
        return ChallengeResponse(
            id=challenge.id,
            action_type=_action_type_value(challenge.action_type),
            status=_status_value(challenge.status),
            initiator_id=challenge.initiator_id,
            co_signer_id=challenge.co_signer_id,
            created_at=challenge.created_at,
            expires_at=challenge.expires_at,
            approved_at=challenge.approved_at,
            consumed_at=challenge.consumed_at,
        )
