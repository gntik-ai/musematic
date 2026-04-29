from __future__ import annotations

from collections.abc import Iterable
from platform.common.exceptions import ValidationError as PlatformValidationError
from platform.common.tagging import dependencies as tagging_dependencies
from platform.common.tagging.dependencies import (
    _requester_id,
    build_visibility_resolver,
    get_label_expression_cache,
    get_label_expression_evaluator,
    get_label_service,
    get_saved_view_service,
    get_tag_service,
    get_tagging_service,
    get_visibility_resolver,
)
from platform.common.tagging.entity_types import get_entity_class, get_entity_type_string
from platform.common.tagging.exceptions import (
    EntityNotFoundForTagError,
    LabelAttachLimitExceededError,
    LabelExpressionSyntaxError,
    SavedViewNameTakenError,
)
from platform.common.tagging.filter_extension import parse_tag_label_filters
from platform.common.tagging.label_expression.parser import parse as parse_label_expression
from platform.common.tagging.repository import TaggingRepository, _sorted_uuids
from platform.common.tagging.schemas import LabelAttachRequest, TagAttachRequest
from platform.registry.models import AgentProfile
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Request
from pydantic import ValidationError as PydanticValidationError


class FakeScalars:
    def __init__(self, values: Iterable[object]) -> None:
        self.values = list(values)

    def all(self) -> list[object]:
        return self.values


class FakeResult:
    def __init__(
        self,
        *,
        scalar_one_or_none: object | None = None,
        scalar_one: object | None = None,
        scalars: Iterable[object] = (),
        all_rows: Iterable[tuple[object, ...]] = (),
        rowcount: int = 0,
    ) -> None:
        self._scalar_one_or_none = scalar_one_or_none
        self._scalar_one = scalar_one if scalar_one is not None else scalar_one_or_none
        self._scalars = list(scalars)
        self._all_rows = list(all_rows)
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> object | None:
        return self._scalar_one_or_none

    def scalar_one(self) -> object:
        return self._scalar_one

    def scalars(self) -> FakeScalars:
        return FakeScalars(self._scalars)

    def all(self) -> list[tuple[object, ...]]:
        return self._all_rows


class FakeSession:
    def __init__(
        self,
        execute_results: Iterable[FakeResult] = (),
        scalar_results: Iterable[int] = (),
    ) -> None:
        self.execute_results = list(execute_results)
        self.scalar_results = list(scalar_results)
        self.added: list[object] = []
        self.executed = 0
        self.flushed = 0

    async def execute(self, _statement: object) -> FakeResult:
        self.executed += 1
        return self.execute_results.pop(0)

    async def scalar(self, _statement: object) -> int:
        return self.scalar_results.pop(0)

    async def flush(self) -> None:
        self.flushed += 1

    def add(self, value: object) -> None:
        self.added.append(value)


def _request(query_string: bytes, *, app: object | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": query_string,
            "app": app,
        }
    )


@pytest.mark.asyncio
async def test_repository_methods_delegate_to_session_and_shape_results() -> None:
    entity_id = uuid4()
    other_id = uuid4()
    tag_row = SimpleNamespace(tag="prod")
    label_row = SimpleNamespace(label_key="env", label_value="prod")
    view_row = SimpleNamespace(id=uuid4())
    session = FakeSession(
        execute_results=[
            FakeResult(scalar_one_or_none=tag_row),
            FakeResult(scalar_one_or_none=tag_row),
            FakeResult(rowcount=1),
            FakeResult(scalars=[tag_row]),
            FakeResult(all_rows=[("agent", entity_id)]),
            FakeResult(scalar_one_or_none=label_row),
            FakeResult(scalar_one=label_row),
            FakeResult(scalar_one_or_none=None),
            FakeResult(rowcount=0),
            FakeResult(scalars=[label_row]),
            FakeResult(scalars=[entity_id]),
            FakeResult(scalars=["env"]),
            FakeResult(scalars=["prod"]),
            FakeResult(),
            FakeResult(),
            FakeResult(scalar_one_or_none=view_row),
            FakeResult(scalars=[view_row]),
            FakeResult(scalars=[view_row]),
            FakeResult(scalar_one_or_none=view_row),
            FakeResult(rowcount=1),
            FakeResult(),
            FakeResult(scalars=[view_row]),
        ],
        scalar_results=[2, 3],
    )
    repo = TaggingRepository(session)  # type: ignore[arg-type]

    assert await repo.get_tag("agent", entity_id, "prod") is tag_row
    assert await repo.insert_tag("agent", entity_id, "prod", None) is tag_row
    assert await repo.delete_tag("agent", entity_id, "prod") is True
    assert await repo.list_tags_for_entity("agent", entity_id) == [tag_row]
    assert await repo.list_entities_by_tag("prod", {"agent": set()}, cursor=None, limit=10) == []
    assert await repo.list_entities_by_tag(
        "prod",
        {"agent": {entity_id}},
        cursor="1",
        limit=10,
    ) == [("agent", entity_id)]
    assert await repo.count_tags_for_entity("agent", entity_id) == 2
    assert await repo.upsert_label("agent", entity_id, "env", "prod", None) == (
        label_row,
        "prod",
    )
    assert await repo.get_label("agent", entity_id, "env") is None
    assert await repo.delete_label("agent", entity_id, "env") is False
    assert await repo.list_labels_for_entity("agent", entity_id) == [label_row]
    assert (
        await repo.filter_entities_by_labels("agent", {}, {entity_id}, cursor=None, limit=10)
        == []
    )
    assert await repo.filter_entities_by_labels(
        "agent",
        {"env": "prod"},
        {entity_id, other_id},
        cursor="0",
        limit=5,
    ) == [entity_id]
    assert await repo.list_label_keys(prefix="e", limit=10) == ["env"]
    assert await repo.list_label_values(key="env", prefix="p", limit=10) == ["prod"]
    assert await repo.count_labels_for_entity("agent", entity_id) == 3

    await repo.cascade_on_entity_deletion("agent", entity_id)
    created = await repo.insert_saved_view(
        owner_id=uuid4(),
        workspace_id=uuid4(),
        name="mine",
        entity_type="agent",
        filters={"labels": {"env": "prod"}},
        shared=False,
    )
    assert session.added == [created]
    assert await repo.get_saved_view(view_row.id) is view_row
    assert await repo.list_personal_views(uuid4(), "agent") == [view_row]
    assert await repo.list_shared_views(uuid4(), "agent") == [view_row]
    assert await repo.update_saved_view(view_row.id, 1, name="renamed") is view_row
    assert await repo.delete_saved_view(view_row.id) is True
    await repo.transfer_saved_view_ownership(view_row.id, uuid4())
    assert await repo.list_views_owned_by_user_in_workspace(uuid4(), uuid4()) == [view_row]
    assert _sorted_uuids({other_id, entity_id}) == sorted([other_id, entity_id], key=str)
    assert session.flushed >= 7


@pytest.mark.asyncio
async def test_visibility_resolver_dependency_providers_cover_empty_and_populated_paths() -> None:
    workspace_id = uuid4()
    entity_ids = [uuid4() for _ in range(6)]
    session = FakeSession(
        execute_results=[
            FakeResult(scalars=[workspace_id]),
            FakeResult(scalars=[workspace_id]),
            FakeResult(scalars=[entity_ids[0]]),
            FakeResult(scalars=[workspace_id]),
            FakeResult(scalars=[entity_ids[1]]),
            FakeResult(scalars=[workspace_id]),
            FakeResult(scalars=[entity_ids[2]]),
            FakeResult(scalars=[workspace_id]),
            FakeResult(scalars=[entity_ids[3]]),
            FakeResult(scalars=[workspace_id]),
            FakeResult(scalars=[entity_ids[4]]),
            FakeResult(scalars=[workspace_id]),
            FakeResult(scalars=[entity_ids[5]]),
        ]
    )
    settings = SimpleNamespace(
        tagging=SimpleNamespace(cross_entity_search_max_visible_ids=20),
    )

    resolver = build_visibility_resolver(session, settings)  # type: ignore[arg-type]
    visible = await resolver.resolve_visible_entity_ids(
        {"sub": str(uuid4())},
        [
            "workspace",
            "agent",
            "fleet",
            "workflow",
            "policy",
            "certification",
            "evaluation_run",
        ],
    )
    empty = await resolver.resolve_visible_entity_ids({}, ["agent", "workspace"])

    assert visible == {
        "workspace": {workspace_id},
        "agent": {entity_ids[0]},
        "fleet": {entity_ids[1]},
        "workflow": {entity_ids[2]},
        "policy": {entity_ids[3]},
        "certification": {entity_ids[4]},
        "evaluation_run": {entity_ids[5]},
    }
    assert empty == {"agent": set(), "workspace": set()}
    assert _requester_id(SimpleNamespace(id=workspace_id)) == workspace_id
    assert _requester_id(object()) is None
    evaluator = await get_label_expression_evaluator()
    assert await evaluator.evaluate(parse_label_expression("env=prod"), {"env": "prod"}) is True


def test_parse_tag_label_filters_and_entity_type_maps() -> None:
    parsed = parse_tag_label_filters(
        _request(b"tags=prod,%20beta,,&label.env=prod&label.tier=gold")
    )

    assert parsed.tags == ["prod", "beta"]
    assert parsed.labels == {"env": "prod", "tier": "gold"}
    assert get_entity_type_string(AgentProfile) == "agent"
    assert get_entity_class("agent") is AgentProfile

    with pytest.raises(PlatformValidationError):
        parse_tag_label_filters(_request(b"tags=bad%20tag"))
    with pytest.raises(PlatformValidationError):
        parse_tag_label_filters(_request(b"label.1bad=value"))


@pytest.mark.asyncio
async def test_dependency_factories_and_schema_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        tagging=SimpleNamespace(
            cross_entity_search_max_visible_ids=20,
            label_expression_lru_size=12,
            label_expression_redis_ttl_seconds=34,
        )
    )
    producer = object()
    request = _request(
        b"",
        app=SimpleNamespace(state=SimpleNamespace(settings=settings, clients={"kafka": producer})),
    )
    session = FakeSession()
    audit = object()
    monkeypatch.setattr(
        tagging_dependencies,
        "build_audit_chain_service",
        lambda used_session, used_settings, used_producer: (
            used_session,
            used_settings,
            used_producer,
            audit,
        ),
    )

    resolver = await get_visibility_resolver(request, session)  # type: ignore[arg-type]
    tag_service = await get_tag_service(request, session)  # type: ignore[arg-type]
    label_service = await get_label_service(request, session)  # type: ignore[arg-type]
    saved_view_service = await get_saved_view_service(session)  # type: ignore[arg-type]
    tagging_service = await get_tagging_service(request, session)  # type: ignore[arg-type]
    label_expression_cache = await get_label_expression_cache(request)

    assert resolver.max_visible_ids == 20
    assert tag_service.max_tags_per_entity == 50
    assert label_service.repository is not None
    assert saved_view_service.repository is not None
    assert tagging_service.tags.max_tags_per_entity == 50
    assert label_expression_cache.lru_size == 12
    assert label_expression_cache.ttl_seconds == 34

    assert TagAttachRequest(tag=" prod ").tag == "prod"
    assert LabelAttachRequest(key=" env ", value=" prod ").model_dump() == {
        "key": "env",
        "value": "prod",
    }
    with pytest.raises(PydanticValidationError):
        TagAttachRequest(tag="bad tag")
    with pytest.raises(PydanticValidationError):
        LabelAttachRequest(key="1bad", value="prod")


def test_tagging_exception_payloads() -> None:
    entity_id = uuid4()
    syntax = LabelExpressionSyntaxError(2, 4, ")", "unexpected token")

    assert LabelAttachLimitExceededError(3).details == {"limit": 3}
    assert SavedViewNameTakenError("mine").status_code == 409
    assert syntax.line == 2
    assert syntax.col == 4
    assert syntax.token == ")"
    assert EntityNotFoundForTagError("agent", entity_id).details == {
        "entity_type": "agent",
        "entity_id": str(entity_id),
    }
