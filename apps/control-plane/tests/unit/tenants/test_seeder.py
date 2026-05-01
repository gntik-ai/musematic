from __future__ import annotations

from platform.tenants.seeder import DEFAULT_TENANT_ID, provision_default_tenant_if_missing
from typing import Any

import pytest


class FakeSession:
    def __init__(self, *, in_transaction: bool) -> None:
        self._in_transaction = in_transaction
        self.executed: list[tuple[Any, dict[str, Any]]] = []
        self.committed = False

    def in_transaction(self) -> bool:
        return self._in_transaction

    async def execute(self, statement: Any, params: dict[str, Any]) -> None:
        self.executed.append((statement, params))

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_seeder_inserts_default_tenant_idempotently_without_transaction() -> None:
    session = FakeSession(in_transaction=False)

    await provision_default_tenant_if_missing(session)  # type: ignore[arg-type]

    statement, params = session.executed[0]
    assert params["id"] == DEFAULT_TENANT_ID
    assert params["slug"] == "default"
    assert params["subdomain"] == "app"
    assert "ON CONFLICT (id) DO NOTHING" in str(statement)
    assert session.committed is True


@pytest.mark.asyncio
async def test_seeder_does_not_commit_existing_transaction() -> None:
    session = FakeSession(in_transaction=True)

    await provision_default_tenant_if_missing(session)  # type: ignore[arg-type]

    assert session.executed
    assert session.committed is False
