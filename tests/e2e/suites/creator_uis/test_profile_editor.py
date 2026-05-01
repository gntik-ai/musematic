from __future__ import annotations

import pytest

from suites._helpers import assert_status

from .conftest import profile_payload, workspace_headers


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_profile_editor_schema_save_preview_and_version(
    http_client,
    workspace,
    mock_llm_responses,
) -> None:
    schema_response = await http_client.get("/api/v1/context-engineering/profiles/schema")
    schema = assert_status(schema_response)
    assert schema["type"] == "object"
    assert "source_config" in schema["properties"]

    create_response = await http_client.post(
        "/api/v1/context-engineering/profiles",
        json=profile_payload("creator-e2e-profile"),
        headers=workspace_headers(workspace["id"]),
    )
    profile = assert_status(create_response, {200, 201})
    assert profile["name"] == "creator-e2e-profile"

    preview_response = await http_client.post(
        f"/api/v1/context-engineering/profiles/{profile['id']}/preview",
        json={"query_text": "creator profile preview"},
        headers=workspace_headers(workspace["id"]),
    )
    preview = assert_status(preview_response)
    assert preview["sources"]
    assert preview["mock_response"]
    assert preview["was_fallback"] in {True, False}

    versions_response = await http_client.get(
        f"/api/v1/context-engineering/profiles/{profile['id']}/versions",
        headers=workspace_headers(workspace["id"]),
    )
    versions = assert_status(versions_response)
    assert versions["versions"][0]["version_number"] == 1
    assert await mock_llm_responses.get_calls("creator profile preview") is not None
