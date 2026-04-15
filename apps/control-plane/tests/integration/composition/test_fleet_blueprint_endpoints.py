from __future__ import annotations


def test_fleet_blueprint_generate_get_and_override(composition_client) -> None:
    client, service = composition_client
    workspace_id = str(service.workspace_id)

    created = client.post(
        "/api/v1/compositions/fleet-blueprint",
        json={"workspace_id": workspace_id, "description": "pipeline team"},
    )
    single = client.post(
        "/api/v1/compositions/fleet-blueprint",
        json={"workspace_id": workspace_id, "description": "single"},
    )
    fetched = client.get(
        f"/api/v1/compositions/fleet-blueprints/{service.fleet_blueprint_id}",
        params={"workspace_id": workspace_id},
    )
    patched = client.patch(
        f"/api/v1/compositions/fleet-blueprints/{service.fleet_blueprint_id}",
        params={"workspace_id": workspace_id},
        json={"overrides": [{"field_path": "topology_type", "new_value": "peer"}]},
    )

    assert created.status_code == 201
    assert created.json()["member_count"] == 3
    assert single.json()["single_agent_suggestion"] is True
    assert fetched.status_code == 200
    assert patched.json()["version"] == 2
