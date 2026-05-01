from __future__ import annotations

import pytest

from suites._helpers import assert_status

from .conftest import workspace_headers


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_creator_can_attach_contract_to_revision_with_profile_present(
    http_client,
    creator_with_profile,
    creator_with_contract,
) -> None:
    profile = creator_with_profile["profile"]
    contract = creator_with_contract["contract"]
    revision = creator_with_contract["revision"]
    workspace_id = creator_with_contract["workspace"]["id"]

    versions_response = await http_client.get(
        f"/api/v1/context-engineering/profiles/{profile['id']}/versions",
        headers=workspace_headers(workspace_id),
    )
    versions = assert_status(versions_response)
    assert versions["versions"][0]["version_number"] >= 1

    if revision is None:
        pytest.skip("seeded E2E agent did not expose a revision payload")

    attach_response = await http_client.post(
        f"/api/v1/trust/contracts/{contract['id']}/attach-revision/{revision['id']}",
    )
    assert attach_response.status_code == 204

    fetched_response = await http_client.get(f"/api/v1/trust/contracts/{contract['id']}")
    fetched = assert_status(fetched_response)
    assert fetched["attached_revision_id"] == revision["id"]
