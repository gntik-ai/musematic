from __future__ import annotations

import pytest

from suites._helpers import assert_status


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_contract_preview_defaults_to_mock_and_real_llm_requires_ack(
    http_client,
    creator_with_contract,
    mock_llm_responses,
) -> None:
    contract = creator_with_contract["contract"]

    mock_response = await http_client.post(
        f"/api/v1/trust/contracts/{contract['id']}/preview",
        json={
            "sample_input": {"output": {"answer": "ok"}, "tokens": 999},
            "use_mock": True,
            "cost_acknowledged": False,
        },
    )
    preview = assert_status(mock_response)
    assert "cost_limit_tokens" in preview["clauses_violated"]
    assert preview["mock_response"]

    rejected = await http_client.post(
        f"/api/v1/trust/contracts/{contract['id']}/preview",
        json={
            "sample_input": {"output": {"answer": "ok"}},
            "use_mock": False,
            "cost_acknowledged": False,
        },
    )
    assert rejected.status_code == 400
    assert await mock_llm_responses.get_calls("contract preview") is not None
