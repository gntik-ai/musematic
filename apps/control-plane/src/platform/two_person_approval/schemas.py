from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CreateChallengeRequest(BaseModel):
    action_type: str = Field(min_length=1, max_length=128)
    action_payload: dict[str, Any] = Field(default_factory=dict)
    ttl_seconds: int = Field(default=300, ge=30, le=3600)


class ChallengeResponse(BaseModel):
    id: UUID
    action_type: str
    status: str
    initiator_id: UUID
    co_signer_id: UUID | None = None
    created_at: datetime
    expires_at: datetime
    approved_at: datetime | None = None
    consumed_at: datetime | None = None


class ApproveChallengeResponse(ChallengeResponse):
    pass


class ConsumeChallengeResponse(BaseModel):
    id: UUID
    action_type: str
    status: str
    action_result: dict[str, Any] = Field(default_factory=dict)
