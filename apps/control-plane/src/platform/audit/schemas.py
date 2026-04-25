from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class VerifyResult(BaseModel):
    valid: bool
    entries_checked: int = Field(ge=0)
    broken_at: int | None = Field(default=None, ge=1)


class AttestationRequest(BaseModel):
    start_seq: int = Field(ge=1)
    end_seq: int = Field(ge=1)


class SignedAttestation(BaseModel):
    platform: str
    env: str
    start_seq: int
    end_seq: int
    start_entry_hash: str
    end_entry_hash: str
    window_start_time: datetime
    window_end_time: datetime
    chain_entries_count: int
    key_version: int = 1
    signature: str


class PublicKeyResponse(BaseModel):
    public_key: str
