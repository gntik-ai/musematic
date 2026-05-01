from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from platform.tenants.models import Tenant
from platform.tenants.repository import TenantsRepository


class ScalarResultStub:
    def __init__(self, item: object | None = None, items: list[object] | None = None) -> None:
        self.item = item
        self.items = items or []

    def scalar_one_or_none(self) -> object | None:
        return self.item

    def scalars(self) -> ScalarResultStub:
        return self

    def all(self) -> list[object]:
        return list(self.items)


class SessionStub:
    def __init__(self) -> None:
        self.get_calls: list[tuple[type[object], object]] = []
        self.execute_calls: list[object] = []
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.flushes = 0
        self.results: list[ScalarResultStub] = []

    async def get(self, model: type[object], identifier: object) -> object:
        self.get_calls.append((model, identifier))
        return SimpleNamespace(id=identifier)

    async def execute(self, statement: object) -> ScalarResultStub:
        self.execute_calls.append(statement)
        return self.results.pop(0) if self.results else ScalarResultStub()

    def add(self, item: object) -> None:
        self.added.append(item)

    async def delete(self, item: object) -> None:
        self.deleted.append(item)

    async def flush(self) -> None:
        self.flushes += 1


@pytest.mark.asyncio
async def test_tenants_repository_crud_and_filtered_listing() -> None:
    session = SessionStub()
    tenant = SimpleNamespace(id=uuid4(), display_name="Acme")
    session.results = [
        ScalarResultStub(item=tenant),
        ScalarResultStub(item=tenant),
        ScalarResultStub(items=[tenant]),
        ScalarResultStub(),
    ]
    repository = TenantsRepository(session)  # type: ignore[arg-type]

    assert await repository.get_by_id(tenant.id) is not None
    assert await repository.get_by_slug("acme") is tenant
    assert await repository.get_by_subdomain("acme") is tenant
    assert await repository.list_all(kind="enterprise", status="active", q="ac", limit=500) == [
        tenant
    ]

    model = Tenant(slug="newco", kind="enterprise", subdomain="newco", display_name="Newco")
    assert await repository.create(model) is model
    assert await repository.update(model, display_name="Newco Ltd") is model
    await repository.delete(model)
    await repository.delete_by_id(uuid4())

    assert session.added == [model]
    assert session.deleted == [model]
    assert session.flushes == 4
    assert len(session.execute_calls) == 4
