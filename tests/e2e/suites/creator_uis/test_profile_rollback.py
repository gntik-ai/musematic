from __future__ import annotations

import pytest

from suites._helpers import assert_status, unique_name

from .conftest import profile_payload, workspace_headers


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_profile_version_history_diff_and_rollback(http_client, creator_with_profile) -> None:
    workspace_id = creator_with_profile["workspace"]["id"]
    profile = creator_with_profile["profile"]
    updated_payload = profile_payload(unique_name("profile-v2"))
    updated_payload["description"] = "Updated profile before rollback"

    update_response = await http_client.put(
        f"/api/v1/context-engineering/profiles/{profile['id']}",
        json=updated_payload,
        headers=workspace_headers(workspace_id),
    )
    updated = assert_status(update_response)
    assert updated["description"] == "Updated profile before rollback"

    diff_response = await http_client.get(
        f"/api/v1/context-engineering/profiles/{profile['id']}/versions/1/diff/2",
        headers=workspace_headers(workspace_id),
    )
    diff = assert_status(diff_response)
    assert "description" in diff["modified"]

    rollback_response = await http_client.post(
        f"/api/v1/context-engineering/profiles/{profile['id']}/rollback/1",
        headers=workspace_headers(workspace_id),
    )
    rollback = assert_status(rollback_response)
    assert rollback["version_number"] == 3
    assert rollback["content_snapshot"]["name"] == profile["name"]
