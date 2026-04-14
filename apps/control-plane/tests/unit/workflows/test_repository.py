from __future__ import annotations

from platform.workflows.models import TriggerType, WorkflowStatus
from platform.workflows.repository import WorkflowRepository
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest


class _ScalarResult:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> object | None:
        return self.value


class _ScalarsResult:
    def __init__(self, values: list[object]) -> None:
        self.values = list(values)

    def scalars(self) -> _ScalarsResult:
        return self

    def all(self) -> list[object]:
        return list(self.values)


def _session(
    *,
    execute_results: list[object] | None = None,
    scalar_results: list[object] | None = None,
) -> Mock:
    session = Mock()
    session.add = Mock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=list(execute_results or []))
    session.scalar = AsyncMock(side_effect=list(scalar_results or []))
    return session


@pytest.mark.asyncio
async def test_workflow_repository_query_methods_return_mocked_results() -> None:
    definition = SimpleNamespace(id=uuid4())
    version = SimpleNamespace(id=uuid4())
    trigger = SimpleNamespace(id=uuid4())
    session = _session(
        execute_results=[
            _ScalarResult(definition),
            _ScalarResult(definition),
            _ScalarsResult([definition]),
            _ScalarResult(version),
            _ScalarResult(version),
            _ScalarsResult([version]),
            _ScalarResult(trigger),
            _ScalarsResult([trigger]),
            _ScalarsResult([trigger]),
        ],
        scalar_results=[3],
    )
    repository = WorkflowRepository(session)  # type: ignore[arg-type]

    assert await repository.get_definition_by_id(uuid4()) is definition
    assert (
        await repository.get_definition_by_name(workspace_id=uuid4(), name="Flow") is definition
    )
    items, total = await repository.list_definitions(
        workspace_id=uuid4(),
        status=WorkflowStatus.active,
        tags=["ops"],
        offset=2,
        limit=10,
    )
    assert items == [definition]
    assert total == 3
    assert await repository.get_version_by_number(uuid4(), 2) is version
    assert await repository.get_version_by_id(version.id) is version
    assert await repository.list_versions(uuid4()) == [version]
    assert await repository.get_trigger_by_id(trigger.id) is trigger
    assert await repository.list_triggers(uuid4()) == [trigger]
    assert await repository.list_active_triggers_by_type(TriggerType.event_bus) == [trigger]


@pytest.mark.asyncio
async def test_workflow_repository_mutation_methods_flush_and_update_fields() -> None:
    session = _session()
    repository = WorkflowRepository(session)  # type: ignore[arg-type]

    definition = SimpleNamespace(current_version_id=None, schema_version=0)
    created_definition = await repository.create_definition(definition)  # type: ignore[arg-type]

    version = SimpleNamespace(id=uuid4())
    created_version = await repository.create_version(version)  # type: ignore[arg-type]
    updated_definition = await repository.update_current_version_id(
        definition,  # type: ignore[arg-type]
        version.id,
        schema_version=2,
    )

    trigger = SimpleNamespace(name="old", is_active=True)
    created_trigger = await repository.create_trigger(trigger)  # type: ignore[arg-type]
    updated_trigger = await repository.update_trigger(
        trigger,  # type: ignore[arg-type]
        name="new",
        is_active=False,
    )
    await repository.delete_trigger(trigger)  # type: ignore[arg-type]

    assert created_definition is definition
    assert created_version is version
    assert updated_definition.current_version_id == version.id
    assert updated_definition.schema_version == 2
    assert created_trigger is trigger
    assert updated_trigger.name == "new"
    assert updated_trigger.is_active is False
    session.add.assert_any_call(definition)
    session.add.assert_any_call(version)
    session.add.assert_any_call(trigger)
    session.delete.assert_awaited_once_with(trigger)
    assert session.flush.await_count == 6
