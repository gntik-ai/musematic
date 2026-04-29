from __future__ import annotations

import hmac
from hashlib import sha256
from platform.workflows.router import (
    archive_workflow,
    create_trigger,
    create_workflow,
    delete_trigger,
    get_version,
    get_workflow,
    invoke_webhook_trigger,
    list_triggers,
    list_versions,
    list_workflows,
    update_trigger,
    update_workflow,
)
from platform.workflows.schemas import TriggerCreate, WorkflowCreate, WorkflowUpdate
from typing import cast
from uuid import uuid4

import pytest
from fastapi import Request
from starlette.datastructures import QueryParams

from tests.unit.workflows.test_service import _build_services


class FakeRequest:
    def __init__(self, payload: dict[str, str]) -> None:
        self._body = b'{"invoice":"INV-1"}'
        self._payload = payload
        self.query_params = QueryParams("")

    async def body(self) -> bytes:
        return self._body

    async def json(self) -> dict[str, str]:
        return self._payload


@pytest.mark.asyncio
async def test_router_functions_cover_workflow_and_webhook_paths() -> None:
    workflow_service, execution_service, _ = _build_services()
    current_user = {"sub": str(uuid4())}
    workspace_id = uuid4()

    created = await create_workflow(
        WorkflowCreate(
            name="Router Workflow",
            description=None,
            yaml_source="""
schema_version: 1
steps:
  - id: fetch
    step_type: agent_task
    agent_fqn: finance.fetcher
            """.strip(),
            tags=[],
            workspace_id=workspace_id,
        ),
        current_user,
        workflow_service,
    )
    listed = await list_workflows(
        cast(Request, FakeRequest({})),
        workspace_id,
        None,
        None,
        1,
        20,
        current_user,
        workflow_service,
    )
    fetched = await get_workflow(created.id, current_user, workflow_service)
    updated = await update_workflow(
        created.id,
        WorkflowUpdate(
            yaml_source="""
schema_version: 1
steps:
  - id: fetch
    step_type: agent_task
    agent_fqn: finance.fetcher
  - id: approve
    step_type: approval_gate
    depends_on: [fetch]
    approval_config:
      required_approvers: [ops]
            """.strip()
        ),
        current_user,
        workflow_service,
    )
    version_one = await get_version(created.id, 1, current_user, workflow_service)
    versions = await list_versions(created.id, current_user, workflow_service)
    trigger = await create_trigger(
        created.id,
        TriggerCreate(
            trigger_type="webhook",
            name="hook",
            config={"secret": "hook-secret"},
        ),
        current_user,
        workflow_service,
    )
    trigger_list = await list_triggers(created.id, current_user, workflow_service)
    updated_trigger = await update_trigger(
        created.id,
        trigger.id,
        TriggerCreate(
            trigger_type="webhook",
            name="hook-updated",
            config={"secret": "hook-secret"},
        ),
        current_user,
        workflow_service,
    )
    request = FakeRequest({"invoice": "INV-1"})
    signature = hmac.new(b"hook-secret", await request.body(), sha256).hexdigest()
    webhook_response = await invoke_webhook_trigger(
        created.id,
        trigger.id,
        cast(Request, request),
        signature,
        workflow_service,
        execution_service,
    )
    await delete_trigger(created.id, trigger.id, current_user, workflow_service)
    archived = await archive_workflow(created.id, current_user, workflow_service)

    assert listed.total == 1
    assert fetched.id == created.id
    assert updated.current_version is not None
    assert version_one.version_number == 1
    assert len(versions) == 2
    assert trigger_list.total == 1
    assert updated_trigger.name == "hook-updated"
    assert "execution_id" in webhook_response
    assert archived.status.value == "archived"
