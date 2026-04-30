from __future__ import annotations

import pytest

from suites._helpers import assert_status

from .conftest import contract_payload


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_contract_editor_schema_enums_and_save(http_client, creator_with_agent) -> None:
    schema_response = await http_client.get("/api/v1/trust/contracts/schema")
    schema = assert_status(schema_response)
    assert "task_scope" in schema["properties"]

    enums_response = await http_client.get("/api/v1/trust/contracts/schema-enums")
    enums = assert_status(enums_response)
    assert enums["resource_types"]
    assert "warn" in enums["failure_modes"]

    agent_payload = creator_with_agent["agent"]
    agent_fqn = agent_payload.get("fqn") or f"{agent_payload['namespace']}:{agent_payload['local_name']}"
    create_response = await http_client.post(
        "/api/v1/trust/contracts",
        json=contract_payload(agent_fqn),
    )
    contract = assert_status(create_response, {200, 201})
    assert contract["agent_id"] == agent_fqn
    assert contract["attached_revision_id"] is None
