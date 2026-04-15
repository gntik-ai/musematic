from __future__ import annotations


def test_agent_blueprint_generate_get_override_and_unavailable(composition_client) -> None:
    client, service = composition_client
    workspace_id = str(service.workspace_id)

    created = client.post(
        "/api/v1/compositions/agent-blueprint",
        json={"workspace_id": workspace_id, "description": "research agent"},
    )
    fetched = client.get(
        f"/api/v1/compositions/agent-blueprints/{service.agent_blueprint_id}",
        params={"workspace_id": workspace_id},
    )
    patched = client.patch(
        f"/api/v1/compositions/agent-blueprints/{service.agent_blueprint_id}",
        params={"workspace_id": workspace_id},
        json={
            "overrides": [
                {
                    "field_path": "model_config.model_id",
                    "new_value": "claude-sonnet-4-6",
                    "reason": "cost optimization",
                }
            ]
        },
    )
    service.unavailable = True
    unavailable = client.post(
        "/api/v1/compositions/agent-blueprint",
        json={"workspace_id": workspace_id, "description": "research agent"},
    )

    assert created.status_code == 201
    assert created.json()["model_config"]["model_id"] == "gpt-test"
    assert fetched.status_code == 200
    assert patched.json()["version"] == 2
    assert patched.json()["model_config"]["model_id"] == "claude-sonnet-4-6"
    assert unavailable.status_code == 503


def test_agent_blueprint_empty_description_rejected(composition_client) -> None:
    client, service = composition_client

    response = client.post(
        "/api/v1/compositions/agent-blueprint",
        json={"workspace_id": str(service.workspace_id), "description": ""},
    )

    assert response.status_code in {400, 422}
