from __future__ import annotations


def test_audit_and_request_endpoints(composition_client) -> None:
    client, service = composition_client
    workspace_id = str(service.workspace_id)

    audit = client.get(
        f"/api/v1/compositions/requests/{service.request_id}/audit",
        params={"workspace_id": workspace_id},
    )
    request = client.get(
        f"/api/v1/compositions/requests/{service.request_id}",
        params={"workspace_id": workspace_id},
    )
    requests = client.get(
        "/api/v1/compositions/requests",
        params={"workspace_id": workspace_id, "request_type": "agent", "status": "completed"},
    )

    assert [item["event_type"] for item in audit.json()["items"]] == [
        "blueprint_generated",
        "blueprint_validated",
    ]
    assert request.json()["status"] == "completed"
    assert requests.json()["items"][0]["request_type"] == "agent"
