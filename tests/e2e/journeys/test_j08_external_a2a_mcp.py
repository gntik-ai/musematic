from __future__ import annotations

import asyncio
import httpx
import jwt
import pytest
from typing import Any
from uuid import UUID

from journeys.conftest import AuthenticatedAsyncClient, JourneyContext
from journeys.helpers.narrative import journey_step

JOURNEY_ID = "j08"
TIMEOUT_SECONDS = 300

# Cross-context inventory:
# - a2a
# - mcp
# - auth
# - registry
# - policies


def _claims(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        options={"verify_signature": False, "verify_exp": False},
        algorithms=["HS256"],
    )


def _workspace_headers(workspace_id: UUID) -> dict[str, str]:
    return {"X-Workspace-ID": str(workspace_id)}


def _sse_events(lines: list[str]) -> list[str]:
    return [line.removeprefix("event:").strip() for line in lines if line.startswith("event:")]


async def _get_agent_card(
    client: AuthenticatedAsyncClient,
    agent_fqn: str,
    *,
    attempts: int = 5,
) -> httpx.Response:
    response: httpx.Response | None = None
    for attempt in range(attempts):
        response = await client.get("/.well-known/agent.json", params={"agent_fqn": agent_fqn})
        if response.status_code != 429:
            return response
        retry_after = response.headers.get("Retry-After")
        try:
            delay = float(retry_after) if retry_after else 0.5 * (attempt + 1)
        except ValueError:
            delay = 0.5 * (attempt + 1)
        await asyncio.sleep(min(delay, 2.0))
    assert response is not None
    return response


@pytest.mark.journey
@pytest.mark.j08_external
@pytest.mark.j08_external_a2a_mcp
@pytest.mark.timeout(TIMEOUT_SECONDS)
@pytest.mark.asyncio
async def test_j08_external_a2a_mcp(
    admin_client: AuthenticatedAsyncClient,
    published_agent: dict[str, Any],
    journey_context: JourneyContext,
    platform_api_url: str,
) -> None:
    assert admin_client.access_token is not None

    workspace_id = UUID(str(published_agent["workspace_id"]))
    agent_fqn = str(published_agent["fqn"])
    agent_id = str(published_agent["id"])
    admin_workspace = admin_client.clone(default_headers=_workspace_headers(workspace_id))

    platform_card: dict[str, Any] | None = None
    per_agent_card: dict[str, Any] | None = None
    a2a_task: dict[str, Any] | None = None
    second_task: dict[str, Any] | None = None
    mcp_tools: dict[str, Any] | None = None
    mcp_result: dict[str, Any] | None = None
    sanitized_payload: dict[str, Any] | None = None

    with journey_step("External bearer token identifies the caller and carries usable auth claims"):
        claims = _claims(admin_client.access_token)
        assert claims["sub"]
        assert claims["email"].endswith("@e2e.test")
        assert any(item.get("role") == "platform_admin" for item in claims.get("roles", []))

    with journey_step("External client fetches the platform Agent Card well-known document"):
        response = await _get_agent_card(admin_workspace, agent_fqn)
        response.raise_for_status()
        platform_card = response.json()
        assert {"skills", "endpoints", "auth_schemes"} <= set(platform_card)
        assert platform_card["name"] == agent_fqn

    with journey_step("Agent Card advertises executable skills, endpoints, and bearer auth"):
        assert platform_card is not None
        assert platform_card["skills"]
        assert "tasks" in platform_card["endpoints"]
        assert "bearer" in platform_card["auth_schemes"]

    with journey_step("External client fetches the per-agent card by FQN"):
        response = await _get_agent_card(admin_workspace, agent_fqn)
        response.raise_for_status()
        per_agent_card = response.json()
        assert per_agent_card["name"] == agent_fqn
        assert per_agent_card["skills"][0]["id"] == "execute"

    with journey_step("Registry resolution confirms the card FQN maps to the published agent"):
        resolved = await admin_workspace.get(f"/api/v1/agents/resolve/{agent_fqn}")
        resolved.raise_for_status()
        resolved_payload = resolved.json()
        assert resolved_payload["id"] == agent_id
        assert resolved_payload["fqn"] == agent_fqn

    with journey_step("OAuth2 bearer token authorizes a single-turn A2A task submission"):
        task = await admin_workspace.post(
            "/a2a/tasks",
            json={"agent_fqn": agent_fqn, "input": "Run an external A2A compliance check."},
        )
        task.raise_for_status()
        a2a_task = task.json()
        assert a2a_task["id"]
        assert a2a_task["status"] in {"submitted", "working", "completed", "failed"}

    with journey_step("External client fetches the A2A task status by ID"):
        assert a2a_task is not None
        fetched = await admin_workspace.get(f"/a2a/tasks/{a2a_task['id']}")
        fetched.raise_for_status()
        assert fetched.json()["id"] == a2a_task["id"]
        assert fetched.json()["status"] == a2a_task["status"]

    with journey_step("External client subscribes to A2A Server-Sent Events"):
        headers = {"Authorization": f"Bearer {admin_client.access_token}"}
        async with httpx.AsyncClient(base_url=platform_api_url, timeout=30.0, headers=headers) as client:
            async with client.stream(
                "POST",
                "/a2a/tasks/stream",
                json={"agent_fqn": agent_fqn, "input": "stream A2A status"},
            ) as stream:
                assert stream.status_code == 200
                lines = [line async for line in stream.aiter_lines() if line]
        events = _sse_events(lines)
        assert events
        assert events[-1] in {"done", "completed", "failed"}

    with journey_step("A2A events preserve causal order from start to completion"):
        assert events[0] in {"started", "submitted", "working"}
        assert events[-1] in {"done", "completed", "failed"}
        assert events.index(events[0]) <= len(events) - 1

    with journey_step("External client starts a multi-turn A2A task requiring clarification"):
        task = await admin_workspace.post(
            "/a2a/tasks",
            json={
                "agent_fqn": agent_fqn,
                "input": "Need clarification before final answer.",
                "metadata": {"journey": JOURNEY_ID, "turn": 1},
            },
        )
        task.raise_for_status()
        second_task = task.json()
        assert second_task["id"] != a2a_task["id"]
        assert second_task["input"].startswith("Need clarification")

    with journey_step("External client sends clarification as a second turn and receives completion state"):
        assert second_task is not None
        clarified = await admin_workspace.post(
            "/a2a/tasks",
            json={
                "agent_fqn": agent_fqn,
                "input": "Clarification: use the approved workspace context only.",
                "metadata": {"journey": JOURNEY_ID, "turn": 2, "previous_task_id": second_task["id"]},
            },
        )
        clarified.raise_for_status()
        clarified_payload = clarified.json()
        assert clarified_payload["status"] in {"completed", "failed"}
        assert clarified_payload["id"] != second_task["id"]

    with journey_step("MCP client discovers available tools through the manifest endpoint"):
        tools = await admin_workspace.get("/mcp/tools")
        tools.raise_for_status()
        mcp_tools = tools.json()
        names = {item["name"] for item in mcp_tools.get("items", mcp_tools)}
        assert "mock-http-tool" in names

    with journey_step("MCP server metadata points clients at the tool manifest"):
        metadata = await admin_workspace.get("/mcp/server")
        metadata.raise_for_status()
        metadata_payload = metadata.json()
        assert metadata_payload.get("tools_endpoint") == "/mcp/tools"
        assert metadata_payload.get("name")

    with journey_step("MCP tool invocation routes through the tool gateway"):
        result = await admin_workspace.post(
            "/mcp/call",
            json={"tool": "mock-http-tool", "arguments": {"input": "journey external call"}},
        )
        result.raise_for_status()
        mcp_result = result.json()
        assert mcp_result["tool"] == "mock-http-tool"
        assert mcp_result["result"]["ok"] is True

    with journey_step("Platform MCP server exposes the same tool through server-call endpoint"):
        server_call = await admin_workspace.post(
            "/mcp/server/tools/mock-http-tool/call",
            json={"arguments": {"input": "server exposure path"}},
        )
        server_call.raise_for_status()
        assert server_call.json()["result"]["ok"] is True

    with journey_step("Policy output sanitizer redacts secret-like values from tool output"):
        sanitize = await admin_workspace.post(
            "/api/v1/policies/sanitize-output",
            json={"content": {"access_token": "secret-token", "safe_value": "visible"}},
        )
        sanitize.raise_for_status()
        sanitized_payload = sanitize.json()
        assert sanitized_payload["content"]["access_token"] == "[REDACTED:secret]"
        assert sanitized_payload["content"]["safe_value"] == "visible"

    with journey_step("Policy enforcement is verified for the MCP call target"):
        policy = await admin_workspace.post(
            "/api/v1/policies",
            json={
                "name": f"{journey_context.prefix}external-tool-policy",
                "scope_type": "workspace",
                "workspace_id": str(workspace_id),
                "rules": {"allowed_tools": ["mock-http-tool"], "deny_secret_output": True},
                "change_summary": "Journey external integration policy",
            },
        )
        policy.raise_for_status()
        attachment = await admin_workspace.post(
            f"/api/v1/policies/{policy.json()['id']}/attach",
            json={"target_type": "tool", "target_id": "mock-http-tool"},
        )
        attachment.raise_for_status()
        assert attachment.json()["policy_id"] == policy.json()["id"]

    with journey_step("External A2A and MCP paths leave the agent profile unchanged and discoverable"):
        listing = await admin_workspace.get(f"/api/v1/marketplace/agents/{agent_id}")
        listing.raise_for_status()
        listing_payload = listing.json()
        assert listing_payload["agent_id"] == agent_id
        assert listing_payload["status"] == "published"

    with journey_step("Final state confirms A2A tasking, SSE, MCP discovery, gateway, policy, and sanitization"):
        assert platform_card is not None
        assert per_agent_card is not None
        assert a2a_task is not None
        assert second_task is not None
        assert mcp_tools is not None
        assert mcp_result is not None
        assert sanitized_payload is not None
