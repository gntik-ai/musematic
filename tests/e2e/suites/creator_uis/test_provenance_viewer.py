from __future__ import annotations

import pytest

from suites._helpers import assert_status

from .conftest import workspace_headers


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_profile_preview_provenance_payload_matches_viewer_contract(
    http_client,
    creator_with_profile,
) -> None:
    workspace_id = creator_with_profile["workspace"]["id"]
    profile = creator_with_profile["profile"]

    response = await http_client.post(
        f"/api/v1/context-engineering/profiles/{profile['id']}/preview",
        json={"query_text": "show memory provenance"},
        headers=workspace_headers(workspace_id),
    )
    payload = assert_status(response)
    first_source = payload["sources"][0]

    assert {"origin", "snippet", "score", "included", "classification"} <= set(first_source)
    assert first_source["classification"] in {"public", "pii", "confidential", "phi", "financial"}
    assert isinstance(first_source["score"], float | int)
