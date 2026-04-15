from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.composition.models import (
    AgentBlueprint,
    CompositionAuditEntry,
    CompositionRequest,
    CompositionValidation,
    FleetBlueprint,
)
from platform.composition.repository import CompositionRepository, apply_cursor
from types import SimpleNamespace
from uuid import uuid4

import pytest


class FakeScalars:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def all(self) -> list[object]:
        return self.items


class FakeResult:
    def __init__(self, one: object | None = None, items: list[object] | None = None) -> None:
        self.one = one
        self.items = items or []

    def scalar_one_or_none(self) -> object | None:
        return self.one

    def scalars(self) -> FakeScalars:
        return FakeScalars(self.items)


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.next_results: list[FakeResult] = []
        self.scalar_value: int | None = 1
        self.flushed = 0
        self.refreshed: list[object] = []

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        self.flushed += 1

    async def refresh(self, item: object, attribute_names: list[str] | None = None) -> None:
        del attribute_names
        self.refreshed.append(item)

    async def execute(self, statement: object) -> FakeResult:
        del statement
        if self.next_results:
            return self.next_results.pop(0)
        return FakeResult()

    async def scalar(self, statement: object) -> int | None:
        del statement
        return self.scalar_value


class FakeColumn:
    def __lt__(self, other: object) -> tuple[str, object]:
        return ("lt", other)


def _request() -> CompositionRequest:
    item = CompositionRequest(
        workspace_id=uuid4(),
        request_type="agent",
        description="d",
        requested_by=uuid4(),
        status="pending",
    )
    item.id = uuid4()
    item.created_at = datetime.now(UTC)
    item.updated_at = datetime.now(UTC)
    return item


def _agent(request: CompositionRequest) -> AgentBlueprint:
    item = AgentBlueprint(
        request_id=request.id,
        workspace_id=request.workspace_id,
        version=1,
        model_config={"model_id": "m"},
        tool_selections=[],
        connector_suggestions=[],
        policy_recommendations=[],
        context_profile={},
        maturity_estimate="developing",
        maturity_reasoning="",
        confidence_score=0.8,
        low_confidence=False,
        follow_up_questions=[],
        llm_reasoning_summary="",
        alternatives_considered=[],
    )
    item.id = uuid4()
    item.request = request
    item.created_at = datetime.now(UTC)
    item.updated_at = datetime.now(UTC)
    return item


def _fleet(request: CompositionRequest) -> FleetBlueprint:
    item = FleetBlueprint(
        request_id=request.id,
        workspace_id=request.workspace_id,
        version=1,
        topology_type="sequential",
        member_count=1,
        member_roles=[],
        orchestration_rules=[],
        delegation_rules=[],
        escalation_rules=[],
        confidence_score=0.8,
        low_confidence=False,
        follow_up_questions=[],
        llm_reasoning_summary="",
        alternatives_considered=[],
        single_agent_suggestion=False,
    )
    item.id = uuid4()
    item.request = request
    item.created_at = datetime.now(UTC)
    item.updated_at = datetime.now(UTC)
    return item


@pytest.mark.asyncio
async def test_repository_create_get_update_and_list_methods() -> None:
    session = FakeSession()
    repo = CompositionRepository(session)
    request = _request()
    agent = _agent(request)
    fleet = _fleet(request)
    session.next_results.extend(
            [
                FakeResult(request),
                FakeResult(request),
                FakeResult(request),
                FakeResult(items=[request, _request()]),
            FakeResult(agent),
            FakeResult(fleet),
            FakeResult(agent),
            FakeResult(fleet),
        ]
    )

    assert await repo.create_request(request) is request
    assert (
        await repo.upsert_request_status(
            request.id,
            request.workspace_id,
            "completed",
            llm_model_used="model",
            generation_time_ms=42,
        )
        is request
    )
    assert await repo.get_request(request.id, request.workspace_id) is request
    items, next_cursor = await repo.list_requests(
        request.workspace_id,
        request_type="agent",
        status="completed",
        cursor=(datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
        limit=1,
    )
    assert len(items) == 1
    assert next_cursor is not None
    assert await repo.get_agent_blueprint(agent.id, request.workspace_id) is agent
    assert await repo.get_fleet_blueprint(fleet.id, request.workspace_id) is fleet
    assert await repo.get_latest_agent_blueprint(request.id, request.workspace_id) is agent
    assert await repo.get_latest_fleet_blueprint(request.id, request.workspace_id) is fleet


@pytest.mark.asyncio
async def test_repository_create_blueprints_validation_audit_and_exists() -> None:
    session = FakeSession()
    repo = CompositionRepository(session)
    request = _request()
    agent = _agent(request)
    fleet = _fleet(request)
    validation = CompositionValidation(
        workspace_id=request.workspace_id,
        agent_blueprint_id=agent.id,
        overall_valid=True,
        tools_check_passed=True,
        tools_check_details={},
        model_check_passed=True,
        model_check_details={},
        connectors_check_passed=True,
        connectors_check_details={},
        policy_check_passed=True,
        policy_check_details={},
    )
    audit = CompositionAuditEntry(
        request_id=request.id,
        workspace_id=request.workspace_id,
        event_type="blueprint_generated",
        actor_id=None,
        payload={},
    )
    audit.id = uuid4()
    audit.created_at = datetime.now(UTC)
    session.next_results.append(FakeResult(items=[audit, CompositionAuditEntry()]))

    assert await repo.create_agent_blueprint(agent) is agent
    assert await repo.create_fleet_blueprint(fleet) is fleet
    assert await repo.insert_validation(validation) is validation
    assert await repo.insert_audit_entry(audit) is audit
    items, next_cursor = await repo.get_audit_entries(
        request.id,
        request.workspace_id,
        event_type_filter="blueprint_generated",
        cursor=(datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        limit=1,
    )
    assert items == [audit]
    assert next_cursor is not None
    assert await repo.request_exists(request.id, request.workspace_id) is True


def test_apply_cursor_returns_query_for_none_cursor() -> None:
    query = SimpleNamespace(where=lambda condition: ("where", condition))
    column = FakeColumn()

    assert apply_cursor(query, object(), None) is query
    assert apply_cursor(query, column, datetime.now(UTC).isoformat())[0] == "where"
