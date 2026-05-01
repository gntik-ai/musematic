from __future__ import annotations

import pytest

from suites._helpers import assert_status, unique_name


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_template_library_lists_platform_templates_and_forks_copy(
    http_client,
    contract_template_seeded,
) -> None:
    templates_response = await http_client.get("/api/v1/trust/contracts/templates")
    templates = assert_status(templates_response)
    assert templates["total"] >= 5
    assert any(item["is_platform_authored"] for item in templates["items"])

    fork_response = await http_client.post(
        f"/api/v1/trust/contracts/{contract_template_seeded['id']}/fork",
        json={"new_name": unique_name("forked-contract")},
    )
    fork = assert_status(fork_response, {200, 201})
    assert (
        fork["escalation_conditions"]["_forked_from_template_id"] == contract_template_seeded["id"]
    )
    assert fork["is_archived"] is False
