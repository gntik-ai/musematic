from __future__ import annotations

from pathlib import Path
from platform.audit.repository import AuditChainRepository
from platform.audit.service import compute_entry_hash
from uuid import uuid4

import pytest


class ScalarSequenceStub:
    def __init__(self, items: list[object]) -> None:
        self._items = items

    def all(self) -> list[object]:
        return list(self._items)


class ExecuteResultStub:
    def __init__(self, scalar: object | None = None, items: list[object] | None = None) -> None:
        self._scalar = scalar
        self._items = items or []
        self.rowcount = 1

    def scalar_one_or_none(self) -> object | None:
        return self._scalar

    def scalars(self) -> ScalarSequenceStub:
        return ScalarSequenceStub(self._items)


class SessionStub:
    def __init__(self) -> None:
        self.execute_results: list[ExecuteResultStub] = []
        self.added: list[object] = []
        self.flush_calls = 0

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flush_calls += 1

    async def execute(self, statement: object) -> ExecuteResultStub:
        del statement
        return self.execute_results.pop(0)


@pytest.mark.asyncio
async def test_audit_repository_update_delete_are_disabled() -> None:
    repository = AuditChainRepository(session=object())  # type: ignore[arg-type]

    with pytest.raises(NotImplementedError):
        await repository.update()
    with pytest.raises(NotImplementedError):
        await repository.delete()


def test_audit_migration_installs_update_delete_blocking_trigger() -> None:
    migration = Path("migrations/versions/058_security_compliance.py").read_text(encoding="utf-8")

    assert "audit_chain_entries_append_only" in migration
    assert "BEFORE UPDATE OR DELETE ON audit_chain_entries" in migration
    assert "RAISE EXCEPTION 'audit_chain_entries is append-only'" in migration
    assert "only allows RTBF nulling of audit_event_id" in migration


@pytest.mark.asyncio
async def test_audit_repository_sql_paths() -> None:
    session = SessionStub()
    repository = AuditChainRepository(session=session)  # type: ignore[arg-type]
    audit_event_id = uuid4()
    entry_hash = compute_entry_hash(
        previous_hash="0" * 64,
        sequence_number=1,
        canonical_payload_hash="a" * 64,
    )
    session.execute_results = [
        ExecuteResultStub(),
        ExecuteResultStub(scalar=3),
        ExecuteResultStub(),
        ExecuteResultStub(items=[]),
        ExecuteResultStub(scalar=None),
        ExecuteResultStub(),
    ]

    await repository.acquire_append_lock()
    assert await repository.next_sequence_number() == 4
    entry = await repository.insert_entry(
        sequence_number=1,
        previous_hash="0" * 64,
        entry_hash=entry_hash,
        audit_event_id=audit_event_id,
        audit_event_source="unit",
        canonical_payload_hash="a" * 64,
    )

    assert await repository.get_latest_entry() is None
    assert await repository.get_by_sequence_range(1, 2) == []
    assert await repository.get_by_sequence(1) is None
    assert await repository.null_audit_event_reference(audit_event_id) == 1
    assert session.added == [entry]
    assert session.flush_calls == 2
