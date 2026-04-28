from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any
from uuid import UUID

import jwt
import pytest

from journeys.conftest import (
    AuthenticatedAsyncClient,
    JourneyContext,
    _register_cleanup,
)
from journeys.helpers.agents import certify_agent, register_full_agent
from journeys.helpers.api_waits import wait_for_policy, wait_for_workspace_access
from journeys.helpers.narrative import journey_step

JOURNEY_ID = "j02"
TIMEOUT_SECONDS = 300

# Cross-context inventory:
# - auth
# - workspaces
# - registry
# - trust
# - marketplace
# - evaluation
# - agentops


def _claims(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        options={"verify_signature": False, "verify_exp": False},
        algorithms=["HS256"],
    )


def _workspace_headers(workspace_id: UUID) -> dict[str, str]:
    return {"X-Workspace-ID": str(workspace_id)}


async def _create_workspace(
    request: pytest.FixtureRequest,
    admin_client: AuthenticatedAsyncClient,
    journey_context: JourneyContext,
    *,
    name_suffix: str,
    description: str,
) -> dict[str, Any]:
    created = await admin_client.post(
        "/api/v1/workspaces",
        json={
            "name": f"{journey_context.prefix}{name_suffix}",
            "description": description,
        },
    )
    created.raise_for_status()
    payload = created.json()
    payload = await wait_for_workspace_access(admin_client, payload["id"])
    _register_cleanup(
        request,
        {
            "kind": "workspace",
            "workspace_id": payload["id"],
            "token": admin_client.access_token,
        },
    )
    return payload


async def _wait_for_marketplace_listing(
    client: AuthenticatedAsyncClient,
    agent_id: str,
    *,
    expected_status: str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    deadline = monotonic() + timeout
    last_status: int | None = None
    last_payload: dict[str, Any] | None = None
    while monotonic() < deadline:
        response = await client.get(f"/api/v1/marketplace/agents/{agent_id}")
        if response.status_code == 200:
            payload = response.json()
            last_payload = payload
            if expected_status is None or payload.get("status") == expected_status:
                return payload
            await asyncio.sleep(1)
            continue
        if response.status_code not in {403, 404}:
            response.raise_for_status()
        last_status = response.status_code
        await asyncio.sleep(1)
    raise AssertionError(
        f"marketplace listing for agent {agent_id} did not become available within {timeout:.0f}s; "
        f"last status={last_status}; last payload={last_payload}"
    )


async def _wait_for_marketplace_search_result(
    client: AuthenticatedAsyncClient,
    *,
    query: str,
    agent_id: str,
    timeout: float = 60.0,
) -> dict[str, Any]:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        response = await client.post(
            "/api/v1/marketplace/search",
            json={"query": query, "page": 1, "page_size": 10},
        )
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("results", []):
            if item.get("agent_id") == agent_id:
                return payload
        await asyncio.sleep(1)
    raise AssertionError(
        f"marketplace search query {query!r} did not return agent {agent_id} within {timeout:.0f}s"
    )


async def _wait_for_evaluation_run(
    client: AuthenticatedAsyncClient,
    run_id: str,
    *,
    timeout: float = 120.0,
) -> dict[str, Any]:
    deadline = monotonic() + timeout
    last_payload: dict[str, Any] | None = None
    while monotonic() < deadline:
        response = await client.get(f"/api/v1/evaluations/runs/{run_id}")
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        if payload["status"] in {"completed", "failed", "canceled"}:
            return payload
        await asyncio.sleep(1)
    raise AssertionError(
        f"evaluation run {run_id} did not reach a terminal state within {timeout:.0f}s; "
        f"last payload={last_payload}"
    )


@pytest.mark.journey
@pytest.mark.j02_creator
@pytest.mark.j02_creator_to_publication
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j02_creator_to_publication(
    request: pytest.FixtureRequest,
    admin_client: AuthenticatedAsyncClient,
    creator_client: AuthenticatedAsyncClient,
    trust_reviewer_client: AuthenticatedAsyncClient,
    journey_context: JourneyContext,
) -> None:
    assert creator_client.access_token is not None

    creator_claims = _claims(creator_client.access_token)
    creator_user_id = UUID(str(creator_claims["sub"]))

    primary_workspace = await _create_workspace(
        request,
        admin_client,
        journey_context,
        name_suffix="creator-primary",
        description="Primary workspace for the creator-to-publication journey.",
    )
    shadow_workspace = await _create_workspace(
        request,
        admin_client,
        journey_context,
        name_suffix="creator-shadow",
        description="Shadow workspace used to validate visibility isolation.",
    )

    primary_workspace_id = UUID(str(primary_workspace["id"]))
    shadow_workspace_id = UUID(str(shadow_workspace["id"]))
    creator_primary = creator_client.clone(default_headers=_workspace_headers(primary_workspace_id))
    creator_shadow = creator_client.clone(default_headers=_workspace_headers(shadow_workspace_id))
    finance_namespace_name = f"{journey_context.prefix}finance-ops"
    shadow_namespace_pattern = f"{journey_context.prefix}shadow:*"

    agent: dict[str, Any] | None = None
    revision_payload: dict[str, Any] | None = None
    attached_policy: dict[str, Any] | None = None
    certification: dict[str, Any] | None = None
    listing_payload: dict[str, Any] | None = None
    eval_set_payload: dict[str, Any] | None = None
    eval_run_payload: dict[str, Any] | None = None
    gate_payload: dict[str, Any] | None = None

    with journey_step("Creator signs in via GitHub OAuth and receives a session token"):
        assert creator_client.refresh_token is not None
        assert creator_claims["sub"]
        assert creator_claims["email"].endswith("@e2e.test")

    with journey_step("Creator session carries workspace-admin RBAC from the GitHub provider mapping"):
        role_names = {item["role"] for item in creator_claims.get("roles", []) if isinstance(item, dict)}
        assert "workspace_admin" in role_names
        assert "platform_admin" not in role_names

    with journey_step("Admin grants the creator access to the primary and shadow workspaces"):
        primary_member = await admin_client.post(
            f"/api/v1/workspaces/{primary_workspace_id}/members",
            json={"user_id": str(creator_user_id), "role": "admin"},
        )
        shadow_member = await admin_client.post(
            f"/api/v1/workspaces/{shadow_workspace_id}/members",
            json={"user_id": str(creator_user_id), "role": "admin"},
        )
        primary_member.raise_for_status()
        shadow_member.raise_for_status()
        assert primary_member.json()["role"] == "admin"
        assert shadow_member.json()["workspace_id"] == str(shadow_workspace_id)
        primary_detail_payload = await wait_for_workspace_access(creator_primary, primary_workspace_id)

    with journey_step("Creator opens the primary workspace and selects the finance-ops namespace"):
        namespace = await creator_primary.post(
            "/api/v1/namespaces",
            json={
                "name": finance_namespace_name,
                "description": "Namespace dedicated to KYC and fraud-screening automations.",
            },
        )
        namespace.raise_for_status()
        assert primary_detail_payload["id"] == str(primary_workspace_id)
        assert namespace.json()["name"] == finance_namespace_name

    with journey_step("Admin narrows primary visibility to finance agents and isolates the shadow workspace"):
        primary_visibility = await admin_client.put(
            f"/api/v1/workspaces/{primary_workspace_id}/visibility",
            json={
                "visibility_agents": [f"{finance_namespace_name}:*"],
                "visibility_tools": ["tool://kyc/*"],
            },
        )
        shadow_visibility = await admin_client.put(
            f"/api/v1/workspaces/{shadow_workspace_id}/visibility",
            json={
                "visibility_agents": [shadow_namespace_pattern],
                "visibility_tools": ["tool://shadow/*"],
            },
        )
        primary_visibility.raise_for_status()
        shadow_visibility.raise_for_status()
        assert primary_visibility.json()["visibility_agents"] == [f"{finance_namespace_name}:*"]
        assert shadow_visibility.json()["visibility_agents"] == [shadow_namespace_pattern]

    with journey_step("Creator registers a KYC verifier with a complete manifest and packaged revision"):
        agent = await register_full_agent(
            creator_primary,
            JOURNEY_ID,
            "finance-ops",
            "kyc-verifier",
            "executor",
            purpose=(
                "Verifies customer identity packages, checks KYC artifacts for completeness, "
                "and escalates suspicious findings with deterministic audit-friendly reasoning."
            ),
            approach=(
                "Deterministic document classification with explicit compliance checks, "
                "tamper heuristics, and explainable escalation notes for human review."
            ),
            tags=["kyc", "verification", "compliance"],
            reasoning_modes=["deterministic", "checklist"],
            display_name="KYC Verifier",
        )
        assert agent["namespace_name"] == finance_namespace_name
        assert agent["local_name"].endswith("kyc-verifier")
        assert ":" in agent["fqn"]

    with journey_step("Creator patches visibility patterns, tags, and descriptive metadata on the agent profile"):
        assert agent is not None
        patched = await creator_primary.patch(
            f"/api/v1/agents/{agent['id']}",
            json={
                "display_name": "KYC Verifier",
                "approach": (
                    "Deterministic KYC verification with document scoring, fraud heuristics, "
                    "and explicit escalation guidance."
                ),
                "tags": ["kyc", "verification", "fraud-screening"],
                "visibility_agents": [f"{finance_namespace_name}:*"],
                "visibility_tools": ["tool://kyc/*"],
            },
        )
        patched.raise_for_status()
        patched_payload = patched.json()
        assert patched_payload["display_name"] == "KYC Verifier"
        assert patched_payload["visibility_agents"] == [f"{finance_namespace_name}:*"]
        assert "fraud-screening" in patched_payload["tags"]

    with journey_step("Registry exposes the immutable revision digest for the uploaded package"):
        assert agent is not None
        profile = await creator_primary.get(f"/api/v1/agents/{agent['id']}")
        revisions = await creator_primary.get(f"/api/v1/agents/{agent['id']}/revisions")
        profile.raise_for_status()
        revisions.raise_for_status()
        profile_payload = profile.json()
        revision_payload = revisions.json()["items"][0]
        assert profile_payload["current_revision"]["id"] == agent["revision_id"]
        assert revision_payload["sha256_digest"]
        assert len(revision_payload["sha256_digest"]) == 64

    with journey_step("FQN resolution returns the newly registered agent with the long-form purpose intact"):
        assert agent is not None
        resolved = await creator_primary.get(f"/api/v1/agents/resolve/{agent['fqn']}")
        resolved.raise_for_status()
        resolved_payload = resolved.json()
        assert resolved_payload["id"] == agent["id"]
        assert len(resolved_payload["purpose"]) >= 50
        assert resolved_payload["approach"] is not None

    with journey_step("Creator authors a workspace policy and attaches it to the uploaded revision"):
        assert revision_payload is not None
        policy = await creator_primary.post(
            "/api/v1/policies",
            json={
                "name": f"{journey_context.prefix}kyc-allow",
                "description": "Allow finance namespace automation for the published KYC verifier.",
                "scope_type": "workspace",
                "workspace_id": str(primary_workspace_id),
                "rules": {
                    "allowed_namespaces": [finance_namespace_name],
                    "allowed_purposes": ["identity verification"],
                },
                "change_summary": "Creator policy for marketplace publication journey",
            },
        )
        policy.raise_for_status()
        policy_payload = await wait_for_policy(creator_primary, policy.json()["id"])
        attached = await creator_primary.post(
            f"/api/v1/policies/{policy_payload['id']}/attach",
            json={
                "target_type": "agent_revision",
                "target_id": str(revision_payload["id"]),
            },
        )
        attached.raise_for_status()
        attached_policy = attached.json()
        assert attached_policy["target_type"] == "agent_revision"
        assert attached_policy["target_id"] == str(revision_payload["id"])

    with journey_step("Trust reviewer approves certification for the current revision with evidence"):
        assert agent is not None
        certification = await certify_agent(
            creator_primary,
            agent["id"],
            reviewer_client=trust_reviewer_client,
            evidence=[
                "Structured KYC fixture package uploaded successfully.",
                "Policy attachment verified before publication.",
            ],
        )
        assert certification["status"] == "active"
        assert certification["certification_id"]

    with journey_step("Certification history shows an active record tied to the current revision"):
        assert agent is not None
        assert revision_payload is not None
        certifications = await creator_primary.get(f"/api/v1/trust/agents/{agent['id']}/certifications")
        certifications.raise_for_status()
        certification_items = certifications.json()["items"]
        assert certification_items
        assert certification_items[0]["status"] == "active"
        assert certification_items[0]["agent_revision_id"] == str(revision_payload["id"])

    with journey_step("Creator promotes the agent lifecycle from draft to validated"):
        assert agent is not None
        validated = await creator_primary.post(
            f"/api/v1/agents/{agent['id']}/transition",
            json={"target_status": "validated", "reason": "Ready for trust-backed publication."},
        )
        validated.raise_for_status()
        assert validated.json()["status"] == "validated"

    with journey_step("Creator raises the maturity level to a production-ready tier"):
        assert agent is not None
        maturity = await creator_primary.post(
            f"/api/v1/agents/{agent['id']}/maturity",
            json={"maturity_level": 3, "reason": "KYC verifier is ready for marketplace publication."},
        )
        maturity.raise_for_status()
        assert maturity.json()["maturity_level"] == 3

    with journey_step("Creator publishes the certified agent to the marketplace"):
        assert agent is not None
        published = await creator_primary.post(
            f"/api/v1/agents/{agent['id']}/transition",
            json={"target_status": "published", "reason": "Certified agent is ready for discovery."},
        )
        published.raise_for_status()
        assert published.json()["status"] == "published"

    with journey_step("Marketplace listing appears in the primary workspace with trust-related fields"):
        assert agent is not None
        listing_payload = await _wait_for_marketplace_listing(
            creator_primary,
            agent["id"],
            expected_status="published",
        )
        quality = await creator_primary.get(f"/api/v1/marketplace/agents/{agent['id']}/quality")
        quality.raise_for_status()
        quality_payload = quality.json()
        assert listing_payload["agent_id"] == agent["id"]
        assert listing_payload["status"] == "published"
        assert listing_payload["certification_status"] != "uncertified" or (
            quality_payload["certification_compliance"] != "uncertified"
        )

    with journey_step("Marketplace intent search for KYC verification finds the published agent"):
        assert agent is not None
        intent_search = await _wait_for_marketplace_search_result(
            creator_primary,
            query="KYC verification",
            agent_id=agent["id"],
        )
        returned_ids = {item["agent_id"] for item in intent_search["results"]}
        assert agent["id"] in returned_ids
        assert intent_search["has_results"] is True

    with journey_step("The same listing is blocked from a shadow workspace outside the configured visibility scope"):
        assert agent is not None
        shadow_listing = await creator_shadow.get(f"/api/v1/marketplace/agents/{agent['id']}")
        assert shadow_listing.status_code == 403
        assert shadow_listing.json()["error"]["code"] == "MARKETPLACE_VISIBILITY_DENIED"

    with journey_step("Registry FQN-pattern discovery returns the published agent in the finance namespace"):
        assert agent is not None
        fqn_pattern = f"{finance_namespace_name}:*"
        discovered = await creator_primary.get(
            "/api/v1/agents",
            params={"status": "published", "fqn_pattern": fqn_pattern, "limit": 20, "offset": 0},
        )
        discovered.raise_for_status()
        discovered_payload = discovered.json()
        discovered_ids = {item["id"] for item in discovered_payload["items"]}
        assert agent["id"] in discovered_ids
        assert discovered_payload["total"] >= 1

    with journey_step("Purpose and approach text remain searchable through registry keyword search"):
        assert agent is not None
        keyword_search = await creator_primary.get(
            "/api/v1/agents",
            params={
                "status": "published",
                "fqn_pattern": f"{finance_namespace_name}:*",
                "keyword": "deterministic compliance checks",
                "limit": 20,
                "offset": 0,
            },
        )
        keyword_search.raise_for_status()
        keyword_ids = {item["id"] for item in keyword_search.json()["items"]}
        assert agent["id"] in keyword_ids

    with journey_step("Creator seeds a minimal evaluation set and benchmark case for the published agent"):
        eval_set = await creator_primary.post(
            "/api/v1/evaluations/eval-sets",
            json={
                "workspace_id": str(primary_workspace_id),
                "name": f"{journey_context.prefix}kyc-smoke",
                "description": "Smoke evaluation for the creator publication journey.",
                "scorer_config": {"exact_match": {"enabled": True}},
                "pass_threshold": 0.1,
            },
        )
        eval_set.raise_for_status()
        eval_set_payload = eval_set.json()
        case = await creator_primary.post(
            f"/api/v1/evaluations/eval-sets/{eval_set_payload['id']}/cases",
            json={
                "input_data": {"prompt": "Verify a customer passport package for completeness."},
                "expected_output": "Verification completed with a compliance-oriented summary.",
                "scoring_criteria": {"exact_match": {"enabled": True}},
                "metadata_tags": {"journey": JOURNEY_ID, "kind": "smoke"},
                "category": "kyc",
            },
        )
        case.raise_for_status()
        assert eval_set_payload["workspace_id"] == str(primary_workspace_id)
        assert case.json()["eval_set_id"] == eval_set_payload["id"]

    with journey_step("Quick evaluation run is created for the published agent and reaches a terminal state"):
        assert agent is not None
        assert eval_set_payload is not None
        run = await creator_primary.post(
            f"/api/v1/evaluations/eval-sets/{eval_set_payload['id']}/run",
            json={"agent_fqn": agent["fqn"], "agent_id": agent["id"]},
        )
        run.raise_for_status()
        eval_run_payload = await _wait_for_evaluation_run(creator_primary, run.json()["id"])
        assert eval_run_payload["agent_fqn"] == agent["fqn"]
        assert eval_run_payload["status"] in {"completed", "failed", "canceled"}

    with journey_step("Evaluation history endpoints store the run and expose per-case verdict data"):
        assert agent is not None
        assert eval_run_payload is not None
        runs = await creator_primary.get(
            "/api/v1/evaluations/runs",
            params={"agent_fqn": agent["fqn"], "page": 1, "page_size": 20},
        )
        verdicts = await creator_primary.get(
            f"/api/v1/evaluations/runs/{eval_run_payload['id']}/verdicts",
            params={"page": 1, "page_size": 20},
        )
        runs.raise_for_status()
        verdicts.raise_for_status()
        run_ids = {item["id"] for item in runs.json()["items"]}
        assert eval_run_payload["id"] in run_ids
        assert verdicts.json()["total"] >= 1

    with journey_step("AgentOps gate-check records the published revision state for downstream promotion decisions"):
        assert agent is not None
        assert revision_payload is not None
        gate = await creator_primary.post(
            f"/api/v1/agentops/{agent['fqn']}/gate-check",
            json={
                "revision_id": str(revision_payload["id"]),
                "workspace_id": str(primary_workspace_id),
            },
        )
        gate.raise_for_status()
        gate_payload = gate.json()
        gate_list = await creator_primary.get(
            f"/api/v1/agentops/{agent['fqn']}/gate-checks",
            params={"revision_id": str(revision_payload["id"]), "limit": 20},
        )
        gate_list.raise_for_status()
        gate_ids = {item["id"] for item in gate_list.json()["items"]}
        assert gate_payload["agent_fqn"] == agent["fqn"]
        assert gate_payload["revision_id"] == str(revision_payload["id"])
        assert gate_payload["id"] in gate_ids

    with journey_step("Final state confirms the agent is certified, published, discoverable, and backed by evaluation history"):
        assert agent is not None
        assert attached_policy is not None
        assert certification is not None
        assert listing_payload is not None
        assert eval_run_payload is not None
        assert gate_payload is not None
        assert revision_payload is not None

        final_profile = await creator_primary.get(f"/api/v1/agents/{agent['id']}")
        final_listing = await creator_primary.get(f"/api/v1/marketplace/agents/{agent['id']}")
        final_certs = await creator_primary.get(f"/api/v1/trust/agents/{agent['id']}/certifications")
        final_runs = await creator_primary.get(
            "/api/v1/evaluations/runs",
            params={"agent_fqn": agent["fqn"], "page": 1, "page_size": 20},
        )
        final_gates = await creator_primary.get(
            f"/api/v1/agentops/{agent['fqn']}/gate-checks",
            params={"revision_id": str(revision_payload['id']), "limit": 20},
        )

        final_profile.raise_for_status()
        final_listing.raise_for_status()
        final_certs.raise_for_status()
        final_runs.raise_for_status()
        final_gates.raise_for_status()

        final_profile_payload = final_profile.json()
        final_listing_payload = final_listing.json()
        final_cert_items = final_certs.json()["items"]
        final_run_items = final_runs.json()["items"]
        final_gate_items = final_gates.json()["items"]

        assert final_profile_payload["status"] == "published"
        assert final_profile_payload["maturity_level"] == 3
        assert final_listing_payload["agent_id"] == agent["id"]
        assert final_listing_payload["status"] == "published"
        assert final_cert_items[0]["id"] == certification["certification_id"]
        assert final_cert_items[0]["status"] == "active"
        assert any(item["id"] == eval_run_payload["id"] for item in final_run_items)
        assert any(item["id"] == gate_payload["id"] for item in final_gate_items)
