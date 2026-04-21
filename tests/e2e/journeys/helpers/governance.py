from __future__ import annotations

from typing import Any


async def _assert_role(
    client,
    *,
    workspace_id: str,
    agent_fqn: str,
    expected_role: str,
) -> dict[str, Any]:
    response = await client.get(
        f"/api/v1/agents/resolve/{agent_fqn}",
        headers={"X-Workspace-ID": str(workspace_id)},
    )
    response.raise_for_status()
    payload = response.json()
    role_types = {str(item).strip() for item in payload.get("role_types", [])}
    if expected_role not in role_types:
        raise AssertionError(
            f"agent {agent_fqn} is missing required role '{expected_role}' (got {sorted(role_types)})"
        )
    return payload


async def create_governance_chain(
    client,
    workspace_id: str,
    observer_fqn: str,
    judge_fqn: str,
    enforcer_fqn: str,
) -> dict[str, Any]:
    await _assert_role(
        client,
        workspace_id=workspace_id,
        agent_fqn=observer_fqn,
        expected_role="observer",
    )
    await _assert_role(
        client,
        workspace_id=workspace_id,
        agent_fqn=judge_fqn,
        expected_role="judge",
    )
    await _assert_role(
        client,
        workspace_id=workspace_id,
        agent_fqn=enforcer_fqn,
        expected_role="enforcer",
    )

    response = await client.put(
        f"/api/v1/workspaces/{workspace_id}/governance-chain",
        json={
            "observer_fqns": [observer_fqn],
            "judge_fqns": [judge_fqn],
            "enforcer_fqns": [enforcer_fqn],
            "policy_binding_ids": [],
            "verdict_to_action_mapping": {},
        },
    )
    response.raise_for_status()
    chain = response.json()
    observer_fqns = list(chain.get("observer_fqns") or [observer_fqn])
    judge_fqns = list(chain.get("judge_fqns") or [judge_fqn])
    enforcer_fqns = list(chain.get("enforcer_fqns") or [enforcer_fqn])
    return {
        "chain_id": chain.get("id"),
        "workspace_id": workspace_id,
        "observer_fqn": observer_fqns[0],
        "judge_fqn": judge_fqns[0],
        "enforcer_fqn": enforcer_fqns[0],
        "observer_fqns": observer_fqns,
        "judge_fqns": judge_fqns,
        "enforcer_fqns": enforcer_fqns,
        "policy_binding_ids": list(chain.get("policy_binding_ids") or []),
        "verdict_to_action_mapping": dict(chain.get("verdict_to_action_mapping") or {}),
        "chain": chain,
    }


async def attach_contract(
    client,
    agent_id: str,
    max_response_time_ms: int,
    min_accuracy: float,
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/trust/contracts",
        json={
            "agent_id": str(agent_id),
            "task_scope": "Journey-driven behavioral contract",
            "quality_thresholds": {"accuracy_min": min_accuracy},
            "time_constraint_seconds": max(1, int(max_response_time_ms / 1000)),
            "enforcement_policy": "warn",
        },
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "contract_id": payload["id"],
        "agent_id": payload["agent_id"],
        "contract": payload,
    }
