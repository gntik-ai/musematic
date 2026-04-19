from __future__ import annotations

from platform.a2a_gateway.models import A2ATaskState
from platform.a2a_gateway.repository import A2AGatewayRepository
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.a2a_gateway_support import (
    ExecuteResultStub,
    SessionStub,
    build_audit_record,
    build_endpoint,
    build_task,
    expired_time,
)


@pytest.mark.asyncio
async def test_repository_create_update_and_delete_helpers() -> None:
    session = SessionStub()
    repo = A2AGatewayRepository(session)  # type: ignore[arg-type]
    task = build_task()
    endpoint = build_endpoint()
    audit = build_audit_record(task_id=task.id)
    blocked = SimpleNamespace(id=uuid4())

    await repo.create_task(task)
    await repo.update_task_state(
        task,
        a2a_state=A2ATaskState.completed,
        result_payload={"ok": True},
        error_code=None,
        error_message=None,
        last_event_id="evt-1",
        idle_timeout_at=None,
    )
    await repo.create_external_endpoint(endpoint)
    await repo.update_external_endpoint_cache(
        endpoint,
        cached_agent_card={"version": "1.0"},
        card_is_stale=True,
        declared_version="1.0",
    )
    await repo.delete_external_endpoint(endpoint)
    await repo.create_audit_record(audit)
    await repo.create_policy_blocked_record(blocked)

    assert session.flush_count == 7
    assert session.added == [task, endpoint, audit, blocked]
    assert task.a2a_state is A2ATaskState.completed
    assert task.result_payload == {"ok": True}
    assert task.last_event_id == "evt-1"
    assert endpoint.cached_agent_card == {"version": "1.0"}
    assert endpoint.card_is_stale is True
    assert endpoint.status == "deleted"


@pytest.mark.asyncio
async def test_repository_query_helpers_return_expected_rows() -> None:
    task = build_task(a2a_state=A2ATaskState.input_required, idle_timeout_at=expired_time())
    endpoint = build_endpoint(workspace_id=task.workspace_id)
    audit = build_audit_record(task_id=task.id)
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(scalar=task),
            ExecuteResultStub(scalar=task),
            ExecuteResultStub(scalar=endpoint),
            ExecuteResultStub(items=[endpoint]),
            ExecuteResultStub(items=[audit]),
            ExecuteResultStub(items=[task]),
        ]
    )
    repo = A2AGatewayRepository(session)  # type: ignore[arg-type]

    assert await repo.get_task_by_task_id(task.task_id) is task
    assert await repo.get_task_by_id(task.id) is task
    assert await repo.get_external_endpoint(endpoint.id, workspace_id=task.workspace_id) is endpoint
    assert await repo.list_external_endpoints(task.workspace_id) == [endpoint]
    assert await repo.list_task_events(task.id) == [audit]
    assert await repo.list_tasks_idle_expired() == [task]


@pytest.mark.asyncio
async def test_repository_update_helpers_accept_none_and_include_deleted_filters() -> None:
    task = build_task(
        result_payload={"ok": True},
        error_code="err",
        error_message="boom",
        last_event_id="evt",
        idle_timeout_at=expired_time(),
        cancellation_requested_at=expired_time(),
    )
    endpoint = build_endpoint(
        status="deleted",
        cached_agent_card={"version": "1.0"},
        declared_version="1.0",
    )
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(scalar=endpoint),
            ExecuteResultStub(items=[endpoint]),
        ]
    )
    repo = A2AGatewayRepository(session)  # type: ignore[arg-type]

    await repo.update_task_state(
        task,
        result_payload=None,
        error_code=None,
        error_message=None,
        last_event_id=None,
        idle_timeout_at=None,
        cancellation_requested_at=None,
    )
    await repo.update_external_endpoint_cache(
        endpoint,
        cached_agent_card=None,
        card_cached_at=None,
        declared_version=None,
        status="active",
    )

    fetched = await repo.get_external_endpoint(endpoint.id, include_deleted=True)
    listed = await repo.list_external_endpoints(endpoint.workspace_id, include_deleted=True)

    assert task.result_payload is None
    assert task.error_code is None
    assert task.error_message is None
    assert task.last_event_id is None
    assert task.idle_timeout_at is None
    assert task.cancellation_requested_at is None
    assert endpoint.cached_agent_card is None
    assert endpoint.card_cached_at is None
    assert endpoint.declared_version is None
    assert endpoint.status == "active"
    assert fetched is endpoint
    assert listed == [endpoint]
