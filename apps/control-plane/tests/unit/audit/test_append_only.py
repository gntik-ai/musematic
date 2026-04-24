from __future__ import annotations

from pathlib import Path
from platform.audit.repository import AuditChainRepository

import pytest


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
