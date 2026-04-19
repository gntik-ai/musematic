from __future__ import annotations

from platform.evaluation.exceptions import (
    RubricBuiltinProtectedError,
    RubricInFlightError,
    RubricNotFoundError,
    RubricValidationError,
)
from platform.evaluation.models import Rubric, RubricStatus
from platform.evaluation.schemas import RubricCreate, RubricCriterion, RubricUpdate
from platform.evaluation.service import RubricService
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from tests.evaluation_testing_support import SessionStub, now_utc


def build_rubric_model(**overrides: object) -> Rubric:
    payload = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "name": "custom-rubric",
        "description": "desc",
        "criteria": [{"name": "accuracy", "description": "desc", "scale_min": 1, "scale_max": 5}],
        "version": 1,
        "is_builtin": False,
        "status": RubricStatus.active,
        "created_by": uuid4(),
        "deleted_at": None,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    payload.update(overrides)
    return Rubric(**payload)


def apply_updates(model: object, **fields: object) -> object:
    for key, value in fields.items():
        setattr(model, key, value)
    return model


def rubric_payload(name: str = "custom-rubric") -> RubricCreate:
    return RubricCreate(
        name=name,
        description="desc",
        criteria=[RubricCriterion(name="accuracy", description="Correctness", scale=5)],
    )


@pytest.mark.asyncio
async def test_rubric_service_creates_and_lists_workspace_rubrics() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    rubric = build_rubric_model(workspace_id=workspace_id, created_by=actor_id)
    repository = SimpleNamespace(
        session=SessionStub(),
        get_workspace_rubric_by_name=AsyncMock(return_value=None),
        create_rubric=AsyncMock(return_value=rubric),
        list_rubrics=AsyncMock(return_value=([rubric], 1)),
    )
    service = RubricService(repository=repository, settings=SimpleNamespace())

    created = await service.create_rubric(rubric_payload(), workspace_id, actor_id)
    listed = await service.list_rubrics(
        workspace_id=workspace_id,
        status=RubricStatus.active,
        include_builtins=True,
        page=1,
        page_size=10,
    )

    assert created.id == rubric.id
    assert listed.total == 1
    assert listed.items[0].name == rubric.name
    assert repository.session.commits == 1


@pytest.mark.asyncio
async def test_rubric_service_updates_and_archives_rubrics() -> None:
    workspace_id = uuid4()
    rubric = build_rubric_model(workspace_id=workspace_id)
    repository = SimpleNamespace(
        session=SessionStub(),
        get_rubric=AsyncMock(side_effect=[rubric, rubric]),
        get_workspace_rubric_by_name=AsyncMock(return_value=None),
        count_in_flight_rubric_references=AsyncMock(side_effect=[0, 0]),
        update_rubric=AsyncMock(side_effect=lambda model, **fields: apply_updates(model, **fields)),
    )
    service = RubricService(repository=repository, settings=SimpleNamespace())

    updated = await service.update_rubric(
        rubric.id,
        RubricUpdate(name="renamed", description="updated"),
        workspace_id=workspace_id,
    )
    await service.archive_rubric(rubric.id, workspace_id=workspace_id)

    assert updated.name == "renamed"
    assert updated.version == 2
    assert rubric.status is RubricStatus.archived
    assert rubric.deleted_at is not None
    assert repository.session.commits == 2


@pytest.mark.asyncio
async def test_rubric_service_rejects_builtin_and_inflight_updates() -> None:
    builtin = build_rubric_model(is_builtin=True)
    mutable = build_rubric_model()
    repository = SimpleNamespace(
        session=SessionStub(),
        get_rubric=AsyncMock(side_effect=[builtin, mutable]),
        count_in_flight_rubric_references=AsyncMock(return_value=1),
    )
    service = RubricService(repository=repository, settings=SimpleNamespace())

    with pytest.raises(RubricBuiltinProtectedError):
        await service.update_rubric(builtin.id, RubricUpdate(name="blocked"))

    with pytest.raises(RubricInFlightError):
        await service.archive_rubric(mutable.id)


@pytest.mark.asyncio
async def test_rubric_service_validates_duplicate_criteria_names() -> None:
    repository = SimpleNamespace(session=SessionStub())
    service = RubricService(repository=repository, settings=SimpleNamespace())
    payload = RubricCreate(
        name="dup",
        description="desc",
        criteria=[
            RubricCriterion(name="same", description="one", scale=5),
            RubricCriterion(name="same", description="two", scale=5),
        ],
    )

    with pytest.raises(RubricValidationError):
        await service._validate_rubric_payload(payload)


@pytest.mark.asyncio
async def test_rubric_service_upserts_builtin_templates_and_lookup_failures() -> None:
    built_in = build_rubric_model(workspace_id=None, is_builtin=True, name="correctness")
    repository = SimpleNamespace(
        session=SessionStub(),
        get_builtin_rubric_by_name=AsyncMock(side_effect=[None, built_in, None]),
        create_rubric=AsyncMock(return_value=built_in),
        update_rubric=AsyncMock(side_effect=lambda model, **fields: apply_updates(model, **fields)),
    )
    service = RubricService(repository=repository, settings=SimpleNamespace())

    created = await service.upsert_builtin_template("correctness", rubric_payload("correctness"))
    updated = await service.upsert_builtin_template("correctness", rubric_payload("correctness"))

    assert created.id == built_in.id
    assert updated.id == built_in.id
    assert repository.session.commits == 2

    with pytest.raises(RubricNotFoundError):
        await service.get_builtin_by_name("missing")


@pytest.mark.asyncio
async def test_rubric_service_detects_duplicate_workspace_names_on_update() -> None:
    workspace_id = uuid4()
    rubric = build_rubric_model(workspace_id=workspace_id, name="primary")
    conflicting = build_rubric_model(workspace_id=workspace_id, name="taken")
    repository = SimpleNamespace(
        session=SessionStub(),
        get_rubric=AsyncMock(return_value=rubric),
        get_workspace_rubric_by_name=AsyncMock(return_value=conflicting),
    )
    service = RubricService(repository=repository, settings=SimpleNamespace())

    with pytest.raises(RubricValidationError, match="already exists"):
        await service.update_rubric(
            rubric.id,
            RubricUpdate(name="taken"),
            workspace_id=workspace_id,
        )
