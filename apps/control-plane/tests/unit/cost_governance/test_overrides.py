from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from platform.common.config import PlatformSettings
from platform.cost_governance.exceptions import (
    OverrideAlreadyRedeemedError,
    OverrideExpiredError,
)
from platform.cost_governance.services.budget_service import BudgetService
from typing import Any
from uuid import UUID, uuid4

import pytest


@dataclass
class OverrideRecord:
    workspace_id: UUID
    issued_by: UUID
    reason: str
    token_hash: str
    expires_at: datetime
    redeemed_by: UUID | None = None
    id: UUID = field(default_factory=uuid4)


class OverrideRepository:
    def __init__(self) -> None:
        self.records: list[OverrideRecord] = []
        self.redeemed: list[tuple[str, UUID | None]] = []

    async def create_override_record(self, **kwargs: Any) -> OverrideRecord:
        record = OverrideRecord(**kwargs)
        self.records.append(record)
        return record

    async def mark_override_redeemed(
        self,
        token_hash: str,
        redeemed_by: UUID | None,
    ) -> OverrideRecord | None:
        self.redeemed.append((token_hash, redeemed_by))
        for record in self.records:
            if record.token_hash == token_hash:
                record.redeemed_by = redeemed_by
                return record
        return None


class AuditRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[Any, ...]] = []

    async def append(self, *payload: Any) -> None:
        self.events.append(payload)


class RedisNonceStore:
    def __init__(self) -> None:
        self.client = self
        self.values: dict[str, bytes] = {}
        self.ttls: dict[str, int | None] = {}
        self.scripts: list[str] = []

    async def initialize(self) -> None:
        return None

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        self.values[key] = value
        self.ttls[key] = ttl

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)

    async def script_load(self, source: str) -> str:
        self.scripts.append(source)
        return f"sha-{len(self.scripts)}"

    async def evalsha(self, sha: str, key_count: int, *args: str) -> bytes | str | None:
        del sha, key_count
        return await self.eval("", 2, *args)

    async def eval(self, source: str, key_count: int, *args: str) -> bytes | str | None:
        del source, key_count
        token_key, redeemed_key, ttl = args
        if redeemed_key in self.values:
            return "already_redeemed"
        value = self.values.get(token_key)
        if value is None:
            return None
        self.values.pop(token_key, None)
        self.values[redeemed_key] = b"1"
        self.ttls[redeemed_key] = int(ttl)
        return value


@pytest.mark.asyncio
async def test_issue_override_writes_redis_nonce_with_ttl_and_audits() -> None:
    repo = OverrideRepository()
    redis = RedisNonceStore()
    audit = AuditRecorder()
    service = BudgetService(
        repository=repo,  # type: ignore[arg-type]
        redis_client=redis,  # type: ignore[arg-type]
        settings=PlatformSettings(cost_governance={"override_token_ttl_seconds": 123}),
        audit_chain_service=audit,
    )

    response = await service.issue_override(uuid4(), uuid4(), "critical backfill")

    assert response.token
    assert list(redis.ttls.values()) == [123]
    assert len(repo.records) == 1
    assert len(audit.events) == 1


@pytest.mark.asyncio
async def test_redeem_override_is_single_shot() -> None:
    repo = OverrideRepository()
    redis = RedisNonceStore()
    service = BudgetService(
        repository=repo,  # type: ignore[arg-type]
        redis_client=redis,  # type: ignore[arg-type]
        settings=PlatformSettings(),
    )
    response = await service.issue_override(uuid4(), uuid4(), "release hotfix")

    await service.redeem_override(response.token, redeemed_by=uuid4())

    with pytest.raises(OverrideAlreadyRedeemedError):
        await service.redeem_override(response.token, redeemed_by=uuid4())
    assert len(repo.redeemed) == 1


@pytest.mark.asyncio
async def test_expired_override_token_raises() -> None:
    service = BudgetService(
        repository=OverrideRepository(),  # type: ignore[arg-type]
        redis_client=RedisNonceStore(),  # type: ignore[arg-type]
        settings=PlatformSettings(),
    )

    with pytest.raises(OverrideExpiredError):
        await service.redeem_override("expired")
