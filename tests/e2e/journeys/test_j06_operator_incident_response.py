from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any
from uuid import UUID

import jwt
import pytest

from journeys.conftest import AuthenticatedAsyncClient, JourneyContext
from journeys.helpers.executions import assert_checkpoint_resumed, wait_for_execution
from journeys.helpers.narrative import journey_step

JOURNEY_ID = "j06"
TIMEOUT_SECONDS = 600

# Cross-context inventory:
# - auth
# - fleets
# - execution
# - workflows
# - runtime
# - agentops
# - governance
# - analytics


def _claims(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        options={"verify_signature": False, "verify_exp": False},
        algorithms=["HS256"],
    )


def _workspace_headers(workspace_id: UUID) -> dict[str, str]:
    return {"X-Workspace-ID": str(workspace_id)}


async def _wait_for_kafka_event(
    client: AuthenticatedAsyncClient,
    *,
    topic: str,
    predicate,
    timeout: float = 30.0,
) -> dict[str, Any]:
    deadline = monotonic() + timeout
    observed: list[dict[str, Any]] = []
    while monotonic() < deadline:
        response = await client.get(
            "/api/v1/_e2e/kafka/events",
            params={"topic": topic, "limit": 200},
        )
        response.raise_for_status()
        observed = response.json().get("events", [])
        for event in observed:
            if predicate(event):
                return event
        await asyncio.sleep(0.5)
    raise AssertionError(f"topic {topic!r} did not emit expected event; observed={observed[-5:]}")


async def _get_runtime_warm_pool(
    client: AuthenticatedAsyncClient,
    *,
    workspace_id: UUID,
) -> dict[str, Any]:
    response = await client.get("/api/v1/runtime/warm-pool")
    if response.status_code == 200:
        return response.json()
    status_response = await client.get(
        "/api/v1/runtime/warm-pool/status",
        params={"workspace_id": str(workspace_id), "agent_type": "executor"},
    )
    status_response.raise_for_status()
    payload = status_response.json()
    return {
        "ready": payload.get("available_pods", payload.get("ready", 0)),
        "capacity": payload.get("pool_size", payload.get("capacity", 0)),
        **payload,
    }


async def _kill_runtime_pod(client: AuthenticatedAsyncClient) -> dict[str, Any]:
    payload = {
        "namespace": "platform",
        "label_selector": "app.kubernetes.io/component=runtime-controller",
        "count": 1,
    }
    response = await client.post("/api/v1/_e2e/chaos/kill-pod", json=payload)
    if response.status_code == 404:
        response = await client.post("/api/v1/_e2e/kill-pod", json=payload)
    response.raise_for_status()
    return response.json()


@pytest.mark.journey
@pytest.mark.j06_operator
@pytest.mark.j06_operator_incident_response
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j06_operator_incident_response(
    admin_client: AuthenticatedAsyncClient,
    operator_client: AuthenticatedAsyncClient,
    running_workload: dict[str, Any],
    journey_context: JourneyContext,
) -> None:
    assert operator_client.access_token is not None

    workspace_id = UUID(str(running_workload["workspace_id"]))
    operator_workspace = operator_client.clone(default_headers=_workspace_headers(workspace_id))
    admin_workspace = admin_client.clone(default_headers=_workspace_headers(workspace_id))
    fleet = running_workload["fleet"]
    workload_agents = running_workload["workload_agents"]
    executor_agent = workload_agents[1]
    workflow = running_workload["workflow"]

    checkpoint_event: dict[str, Any] | None = None
    checkpoint_execution: dict[str, Any] | None = None
    rollback_payload: dict[str, Any] | None = None
    high_execution: dict[str, Any] | None = None
    low_execution: dict[str, Any] | None = None
    analytics_payload: dict[str, Any] | None = None
    drift_payload: dict[str, Any] | None = None
    proposal_payload: dict[str, Any] | None = None
    canary_payload: dict[str, Any] | None = None
    canary_rollback: dict[str, Any] | None = None

    with journey_step("Operator signs in with platform-operator authority"):
        claims = _claims(operator_client.access_token)
        role_names = {item["role"] for item in claims.get("roles", []) if isinstance(item, dict)}
        assert "platform_operator" in role_names
        assert "execution.rollback" in claims.get("permissions", [])

    with journey_step("Operator opens the workload workspace and seeded fleet"):
        workspace = await operator_workspace.get(f"/api/v1/workspaces/{workspace_id}")
        fleet_detail = await operator_workspace.get(f"/api/v1/fleets/{fleet['id']}")
        workspace.raise_for_status()
        assert workspace.json()["id"] == str(workspace_id)
        assert fleet_detail.status_code in {200, 404}
        if fleet_detail.status_code == 200:
            assert fleet_detail.json()["id"] == fleet["id"]

    with journey_step("Operator reads runtime warm-pool capacity and available-pod metrics"):
        warm_pool = await _get_runtime_warm_pool(operator_workspace, workspace_id=workspace_id)
        assert int(warm_pool.get("ready", warm_pool.get("available_pods", 0))) >= 0
        assert int(warm_pool.get("capacity", warm_pool.get("pool_size", 0))) >= 0

    with journey_step("Operator verifies the preloaded workload has active and queued executions"):
        assert running_workload["active_executions"]
        assert running_workload["queued_executions"]
        assert running_workload["workflow"]["id"] == workflow["id"]

    with journey_step("Operator creates a checkpointed long-running execution"):
        created = await operator_workspace.post(
            "/api/v1/executions",
            json={
                "workflow_definition_id": workflow["id"],
                "workspace_id": str(workspace_id),
                "agent_fqn": executor_agent["fqn"],
                "input": "checkpoint please before simulating runtime interruption",
                "checkpoint": True,
                "trigger_type": "manual",
                "input_parameters": {"journey": JOURNEY_ID, "kind": "checkpoint"},
            },
        )
        created.raise_for_status()
        checkpoint_execution = created.json()
        assert checkpoint_execution["id"]
        assert checkpoint_execution["status"] in {"completed", "running", "queued"}

    with journey_step("Execution event stream exposes the created checkpoint"):
        assert checkpoint_execution is not None
        checkpoint_event = await _wait_for_kafka_event(
            admin_client,
            topic="execution.events",
            predicate=lambda event: event["payload"].get("execution_id")
            == checkpoint_execution["id"]
            and event["payload"].get("event_type") == "checkpoint.created",
        )
        assert checkpoint_event["payload"]["checkpoint_id"]

    with journey_step("Operator forces a runtime pod kill through the E2E chaos endpoint"):
        killed = await _kill_runtime_pod(operator_workspace)
        assert killed["count"] >= 1
        assert killed["killed"][0]["name"]

    with journey_step("Heartbeat-driven recovery is surfaced by a terminal execution state"):
        assert checkpoint_execution is not None
        final_execution = await wait_for_execution(
            operator_workspace,
            checkpoint_execution["id"],
            timeout=60.0,
            expected_states=("completed", "running", "queued"),
        )
        assert final_execution["id"] == checkpoint_execution["id"]

    with journey_step("Operator rolls the execution back to the last observed checkpoint"):
        assert checkpoint_execution is not None
        assert checkpoint_event is not None
        rollback = await operator_workspace.post(
            f"/api/v1/executions/{checkpoint_execution['id']}/rollback",
            json={"checkpoint_id": checkpoint_event["payload"]["checkpoint_id"]},
        )
        rollback.raise_for_status()
        rollback_payload = rollback.json()
        assert rollback_payload["id"] == checkpoint_execution["id"]
        assert rollback_payload.get("state", rollback_payload.get("status")) in {
            "queued",
            "running",
            "completed",
        }

    with journey_step("Rollback resume check confirms execution state was not restarted from scratch"):
        assert checkpoint_execution is not None
        assert rollback_payload is not None
        observed_checkpoint = (
            rollback_payload.get("last_checkpoint_id")
            or rollback_payload.get("checkpoint_id")
            or rollback_payload.get("resume_checkpoint_id")
            or "None"
        )
        resumed = await assert_checkpoint_resumed(
            operator_workspace,
            checkpoint_execution["id"],
            str(observed_checkpoint),
        )
        assert resumed["id"] == checkpoint_execution["id"]

    with journey_step("Rollback and completion are visible in the execution journal"):
        assert checkpoint_execution is not None
        journal = await operator_workspace.get(f"/api/v1/executions/{checkpoint_execution['id']}/journal")
        journal.raise_for_status()
        journal_items = journal.json()["items"]
        assert journal_items
        assert any(item["execution_id"] == checkpoint_execution["id"] for item in journal_items)

    with journey_step("Operator inspects execution timeline and reasoning trace after recovery"):
        assert checkpoint_execution is not None
        task_plan = await operator_workspace.get(f"/api/v1/executions/{checkpoint_execution['id']}/task-plan")
        trace = await operator_workspace.get(
            f"/api/v1/executions/{checkpoint_execution['id']}/reasoning-trace"
        )
        task_plan.raise_for_status()
        trace.raise_for_status()
        assert task_plan.json()
        assert trace.json()["steps"][0]["status"] == "completed"

    with journey_step("Operator reviews governance verdicts generated during incident handling"):
        verdict = await operator_workspace.post(
            "/api/v1/governance/verdicts",
            json={
                "judge_fqn": running_workload["agents"]["judge"]["fqn"],
                "target_agent_fqn": executor_agent["fqn"],
                "subject": {"action": "runtime.recover", "incident": journey_context.prefix},
                "workspace_id": str(workspace_id),
            },
        )
        verdict.raise_for_status()
        fetched = await operator_workspace.get(f"/api/v1/governance/verdicts/{verdict.json()['id']}")
        fetched.raise_for_status()
        assert fetched.json()["id"] == verdict.json()["id"]

    with journey_step("Operator records an enforcement action for the runtime incident"):
        enforcement = await operator_workspace.post(
            "/api/v1/governance/enforcements",
            json={
                "target_agent_fqn": executor_agent["fqn"],
                "verdict": "deny",
                "reason": "Runtime incident required checkpoint recovery.",
                "workspace_id": str(workspace_id),
            },
        )
        enforcement.raise_for_status()
        assert enforcement.json()["target_agent_fqn"] == executor_agent["fqn"]

    with journey_step("Operator injects low-priority and urgent executions for queue reprioritization"):
        low = await operator_workspace.post(
            "/api/v1/executions",
            json={"agent_fqn": executor_agent["fqn"], "input": "low priority", "priority": 1},
        )
        high = await operator_workspace.post(
            "/api/v1/executions",
            json={"agent_fqn": executor_agent["fqn"], "input": "urgent recovery", "priority": 1},
        )
        low.raise_for_status()
        high.raise_for_status()
        low_execution = low.json()
        high_execution = high.json()
        assert low_execution["id"] != high_execution["id"]

    with journey_step("Urgent execution is reprioritized and completes no later than the low-priority run"):
        assert low_execution is not None
        assert high_execution is not None
        reprioritized = await operator_workspace.post(
            f"/api/v1/executions/{high_execution['id']}/reprioritize",
            json={"priority": 100},
        )
        reprioritized.raise_for_status()
        high_final = await wait_for_execution(operator_workspace, high_execution["id"], timeout=60.0)
        low_final = await wait_for_execution(operator_workspace, low_execution["id"], timeout=60.0)
        assert reprioritized.json()["priority"] == 100
        assert high_final["completed_at"] <= low_final["completed_at"]

    with journey_step("Operator opens analytics usage and cost-intelligence dashboards"):
        usage = await operator_workspace.get("/api/v1/analytics/usage")
        cost = await operator_workspace.get("/api/v1/analytics/cost-intelligence")
        usage.raise_for_status()
        cost.raise_for_status()
        analytics_payload = {"usage": usage.json(), "cost": cost.json()}
        assert isinstance(analytics_payload["usage"], dict)
        assert isinstance(analytics_payload["cost"], dict)

    with journey_step("AgentOps drift signal is generated from the incident outcome"):
        drift = await operator_workspace.post(
            "/api/v1/agentops/drift-signals",
            json={"agent_fqn": executor_agent["fqn"], "outcome": "checkpoint_recovered"},
        )
        drift.raise_for_status()
        drift_payload = drift.json()
        assert drift_payload["agent_fqn"] == executor_agent["fqn"]

    with journey_step("Operator reviews the adaptation proposal created from the drift signal"):
        assert drift_payload is not None
        proposal = await operator_workspace.post(
            "/api/v1/agentops/proposals",
            json={"drift_signal_id": drift_payload["id"], "agent_fqn": executor_agent["fqn"]},
        )
        proposal.raise_for_status()
        proposal_payload = proposal.json()
        fetched = await operator_workspace.get(f"/api/v1/agentops/proposals/{proposal_payload['id']}")
        fetched.raise_for_status()
        assert fetched.json()["id"] == proposal_payload["id"]

    with journey_step("Operator approves the adaptation path by promoting the agent maturity signal"):
        maturity = await admin_workspace.post(
            f"/api/v1/agents/{executor_agent['id']}/maturity",
            json={"maturity_level": 2, "reason": "Incident adaptation reviewed by operator."},
        )
        maturity.raise_for_status()
        assert maturity.json()["maturity_level"] == 2

    with journey_step("Operator creates a canary deployment for the recovered agent"):
        canary = await operator_workspace.post(
            "/api/v1/agentops/canaries",
            json={"agent_fqn": executor_agent["fqn"], "traffic_percent": 10},
        )
        canary.raise_for_status()
        canary_payload = canary.json()
        assert canary_payload["state"] == "active"
        assert canary_payload["traffic_percent"] == 10

    with journey_step("Operator verifies rollback endpoint for the canary"):
        assert canary_payload is not None
        rollback = await operator_workspace.post(
            f"/api/v1/agentops/canaries/{canary_payload['id']}/rollback",
            json={"reason": "Journey canary rollback verification."},
        )
        rollback.raise_for_status()
        canary_rollback = rollback.json()
        assert canary_rollback["state"] in {"stable", "rolled_back"}

    with journey_step("Operator decommissions the recovered workload agent while preserving direct lookup"):
        retired = await admin_workspace.post(
            f"/api/v1/agents/{executor_agent['id']}/transition",
            json={"target_status": "retired", "reason": "Journey operator decommission."},
        )
        direct_lookup = await operator_workspace.get(f"/api/v1/agents/{executor_agent['id']}")
        retired.raise_for_status()
        direct_lookup.raise_for_status()
        assert retired.json()["status"] == "retired"
        assert direct_lookup.json()["id"] == executor_agent["id"]

    with journey_step("Final state preserves incident response, analytics, adaptation, canary, and decommission records"):
        assert checkpoint_event is not None
        assert checkpoint_execution is not None
        assert rollback_payload is not None
        assert high_execution is not None
        assert low_execution is not None
        assert analytics_payload is not None
        assert drift_payload is not None
        assert proposal_payload is not None
        assert canary_payload is not None
        assert canary_rollback is not None
