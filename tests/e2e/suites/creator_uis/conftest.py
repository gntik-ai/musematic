from __future__ import annotations

from typing import Any

import pytest

from suites._helpers import assert_status, unique_name


def workspace_headers(workspace_id: str) -> dict[str, str]:
    return {"X-Workspace-ID": workspace_id}


def profile_payload(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "description": "Creator UI E2E context profile",
        "source_config": [
            {
                "source_type": "long_term_memory",
                "priority": 80,
                "enabled": True,
                "max_elements": 10,
                "retrieval_strategy": "hybrid",
                "provenance_enabled": True,
                "provenance_classification": "public",
                "provenance_attribution": "Workspace memory",
            }
        ],
        "budget_config": {"max_tokens_step": 2048, "max_sources": 5},
        "compaction_strategies": ["relevance_truncation"],
        "quality_weights": {"relevance": 0.8},
        "privacy_overrides": {},
        "is_default": False,
    }


def contract_payload(agent_fqn: str) -> dict[str, Any]:
    return {
        "agent_id": agent_fqn,
        "task_scope": "Answer creator test prompts using approved context only.",
        "expected_outputs": {"required": ["answer", "citations"]},
        "quality_thresholds": {"minimum_confidence": 0.7},
        "time_constraint_seconds": 30,
        "cost_limit_tokens": 500,
        "escalation_conditions": {"secret_detected": "terminate"},
        "success_criteria": {"requires_citation": True},
        "enforcement_policy": "warn",
    }


@pytest.fixture
async def creator_with_agent(http_client, workspace, agent) -> dict[str, Any]:
    created = await agent.register(
        "creator-ui",
        unique_name("agent"),
        "executor",
        workspace_id=workspace["id"],
    )
    revisions = await http_client.get(f"/api/v1/agents/{created['id']}/revisions")
    revision_payload = None
    if revisions.status_code == 200:
        items = revisions.json().get("items", [])
        revision_payload = items[0] if items else None
    return {"workspace": workspace, "agent": created, "revision": revision_payload}


@pytest.fixture
async def creator_with_profile(http_client, creator_with_agent) -> dict[str, Any]:
    workspace = creator_with_agent["workspace"]
    response = await http_client.post(
        "/api/v1/context-engineering/profiles",
        json=profile_payload(unique_name("profile")),
        headers=workspace_headers(workspace["id"]),
    )
    profile = assert_status(response, {200, 201})
    return {**creator_with_agent, "profile": profile}


@pytest.fixture
async def creator_with_contract(http_client, creator_with_agent) -> dict[str, Any]:
    agent_payload = creator_with_agent["agent"]
    agent_fqn = (
        agent_payload.get("fqn") or f"{agent_payload['namespace']}:{agent_payload['local_name']}"
    )
    response = await http_client.post(
        "/api/v1/trust/contracts",
        json=contract_payload(agent_fqn),
    )
    contract = assert_status(response, {200, 201})
    return {**creator_with_agent, "contract": contract}


@pytest.fixture
async def mock_llm_responses(mock_llm) -> Any:
    await mock_llm.set_response("creator profile preview", "mock creator profile response")
    await mock_llm.set_response("contract preview", "mock contract preview response")
    return mock_llm


@pytest.fixture
async def contract_template_seeded(http_client) -> dict[str, Any]:
    response = await http_client.get("/api/v1/trust/contracts/templates")
    payload = assert_status(response)
    assert payload["total"] >= 5
    return payload["items"][0]
