from __future__ import annotations


def test_validation_endpoints_return_agent_pass_and_fleet_cycle(composition_client) -> None:
    client, service = composition_client
    workspace_id = str(service.workspace_id)

    agent = client.post(
        f"/api/v1/compositions/agent-blueprints/{service.agent_blueprint_id}/validate",
        params={"workspace_id": workspace_id},
    )
    fleet = client.post(
        f"/api/v1/compositions/fleet-blueprints/{service.fleet_blueprint_id}/validate",
        params={"workspace_id": workspace_id},
    )

    assert agent.status_code == 200
    assert agent.json()["overall_valid"] is True
    assert fleet.status_code == 200
    assert fleet.json()["overall_valid"] is False
    assert fleet.json()["cycle_check"]["details"]["cycles_found"][0]["path"] == ["a", "b", "a"]
