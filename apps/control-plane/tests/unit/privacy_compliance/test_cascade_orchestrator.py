from __future__ import annotations

import json
from datetime import UTC, datetime
from platform.privacy_compliance.cascade_adapters.base import CascadeAdapter, CascadeResult
from platform.privacy_compliance.exceptions import CascadePartialFailure
from platform.privacy_compliance.services.cascade_orchestrator import CascadeOrchestrator
from platform.privacy_compliance.services.tombstone_signer import TombstoneSigner
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class Adapter(CascadeAdapter):
    def __init__(self, store_name: str, affected: int, *, fail: bool = False) -> None:
        self.store_name = store_name
        self.affected = affected
        self.fail = fail
        self.calls: list[UUID] = []

    async def dry_run(self, subject_user_id: UUID):
        from platform.privacy_compliance.cascade_adapters.base import CascadePlan

        return CascadePlan(self.store_name, self.affected, {self.store_name: self.affected})

    async def execute(self, subject_user_id: UUID) -> CascadeResult:
        self.calls.append(subject_user_id)
        if self.fail:
            raise RuntimeError("boom")
        now = datetime.now(UTC)
        return CascadeResult(
            self.store_name,
            now,
            now,
            self.affected,
            {self.store_name: self.affected},
            [],
        )


class Repo:
    def __init__(self) -> None:
        self.tombstone = None

    async def insert_tombstone(self, **kwargs):
        self.tombstone = SimpleNamespace(id=uuid4(), **kwargs)
        return self.tombstone

    async def get_tombstone(self, tombstone_id):
        del tombstone_id
        return self.tombstone


class Salt:
    async def get_current_salt(self) -> bytes:
        return b"salt"

    async def get_current_version(self) -> int:
        return 1


class Audit:
    def __init__(self) -> None:
        self.calls = []

    async def append(self, audit_event_id, source, canonical_payload):
        self.calls.append((audit_event_id, source, canonical_payload))


@pytest.mark.asyncio
async def test_orchestrator_runs_adapters_in_store_order_and_hashes_tombstone() -> None:
    repo = Repo()
    audit = Audit()
    orchestrator = CascadeOrchestrator(
        repository=repo,
        adapters=[
            Adapter("neo4j", 1),
            Adapter("postgresql", 2),
            Adapter("qdrant", 3),
            Adapter("opensearch", 4),
            Adapter("s3", 5),
            Adapter("clickhouse", 6),
        ],
        signer=TombstoneSigner(),
        salt_provider=Salt(),
        audit_chain=audit,
    )

    plan = await orchestrator.run(uuid4(), uuid4(), dry_run=True)
    assert plan.store_name
    tombstone = await orchestrator.run(uuid4(), uuid4())
    signed = await orchestrator.export_signed(tombstone.id)

    assert tombstone.proof_hash
    assert signed.signature
    assert audit.calls
    assert [entry["store_name"] for entry in tombstone.cascade_log] == [
        "postgresql",
        "qdrant",
        "opensearch",
        "s3",
        "clickhouse",
        "neo4j",
    ]
    payload = json.loads(orchestrator._canonical_json_from_tombstone(tombstone))
    assert payload["subject_user_id_hash"] == tombstone.subject_user_id_hash
    assert "subject_user_id" not in payload


@pytest.mark.asyncio
async def test_partial_failure_still_persists_tombstone() -> None:
    repo = Repo()
    orchestrator = CascadeOrchestrator(
        repository=repo,
        adapters=[Adapter("postgresql", 1), Adapter("qdrant", 0, fail=True)],
        signer=TombstoneSigner(),
        salt_provider=Salt(),
    )

    with pytest.raises(CascadePartialFailure):
        await orchestrator.run(uuid4(), uuid4())

    assert repo.tombstone is not None
    assert any(entry["status"] == "failed" for entry in repo.tombstone.cascade_log)
