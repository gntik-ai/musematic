from __future__ import annotations

import hmac
from hashlib import sha256
from uuid import UUID, uuid4

import pytest

from tests.integration.conftest import WorkflowExecutionStack


@pytest.mark.asyncio
async def test_workflow_crud_trigger_and_webhook_flow(
    workflow_execution_client,
    workflow_execution_stack: WorkflowExecutionStack,
) -> None:
    workspace_id = uuid4()
    create_response = await workflow_execution_client.post(
        "/api/v1/workflows",
        json={
            "name": "Invoice Pipeline",
            "description": "Validates invoice payloads",
            "yaml_source": """
schema_version: 1
steps:
  - id: fetch_invoice
    step_type: agent_task
    agent_fqn: finance.fetcher
            """.strip(),
            "tags": ["finance"],
            "workspace_id": str(workspace_id),
        },
    )

    assert create_response.status_code == 201
    created_payload = create_response.json()
    workflow_id = UUID(created_payload["id"])
    assert created_payload["current_version"]["version_number"] == 1

    update_response = await workflow_execution_client.patch(
        f"/api/v1/workflows/{workflow_id}",
        json={
            "yaml_source": """
schema_version: 1
steps:
  - id: fetch_invoice
    step_type: agent_task
    agent_fqn: finance.fetcher
  - id: approve_invoice
    step_type: approval_gate
    depends_on: [fetch_invoice]
    approval_config:
      required_approvers: [ops]
            """.strip(),
            "change_summary": "add approval gate",
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["current_version"]["version_number"] == 2

    version_one_response = await workflow_execution_client.get(
        f"/api/v1/workflows/{workflow_id}/versions/1",
    )
    assert version_one_response.status_code == 200
    assert version_one_response.json()["version_number"] == 1

    cron_trigger_response = await workflow_execution_client.post(
        f"/api/v1/workflows/{workflow_id}/triggers",
        json={
            "trigger_type": "cron",
            "name": "Nightly sync",
            "config": {
                "cron": "0 5 * * *",
                "timezone": "UTC",
            },
        },
    )
    assert cron_trigger_response.status_code == 201

    webhook_trigger_response = await workflow_execution_client.post(
        f"/api/v1/workflows/{workflow_id}/triggers",
        json={
            "trigger_type": "webhook",
            "name": "Invoice webhook",
            "config": {"secret": "hook-secret"},
        },
    )
    assert webhook_trigger_response.status_code == 201
    webhook_trigger_id = webhook_trigger_response.json()["id"]

    raw_payload = b'{"invoice":"INV-1"}'
    signature = hmac.new(b"hook-secret", raw_payload, sha256).hexdigest()
    accepted = await workflow_execution_client.post(
        f"/api/v1/workflows/{workflow_id}/webhook/{webhook_trigger_id}",
        content=raw_payload,
        headers={
            "content-type": "application/json",
            "x-webhook-signature": signature,
        },
    )
    rejected = await workflow_execution_client.post(
        f"/api/v1/workflows/{workflow_id}/webhook/{webhook_trigger_id}",
        content=raw_payload,
        headers={
            "content-type": "application/json",
            "x-webhook-signature": "not-valid",
        },
    )

    assert accepted.status_code == 202
    execution_id = UUID(accepted.json()["execution_id"])
    stored_execution = await workflow_execution_stack.execution_repository.get_execution_by_id(
        execution_id
    )
    assert stored_execution is not None
    assert rejected.status_code == 401

    archive_response = await workflow_execution_client.post(
        f"/api/v1/workflows/{workflow_id}/archive",
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "archived"

    active_list_response = await workflow_execution_client.get(
        "/api/v1/workflows",
        params={"workspace_id": str(workspace_id), "status": "active"},
    )
    assert active_list_response.status_code == 200
    assert active_list_response.json()["total"] == 0
